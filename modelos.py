"""
Banco de dados (SQLite via Flask-SQLAlchemy).

Três tabelas:

    pessoas      quem é o acolhido (dados que não mudam de uma internação para outra)
       │ 1
       │ N
    internacoes  cada passagem pela casa: começa como triagem (em admissão, lista de
       │ 1       espera, desistência) e, ao ser admitida, vira internação (ativo/inativo).
       │ N       Responsável, convênio e datas ficam aqui — mudam a cada internação.
    parcelas     contribuições pagas naquela internação (nº, data, valor)

Os nomes das colunas são os mesmos dos campos dos formulários (name="..."):
    preencher(form)      formulário -> colunas (só os campos que vieram no form)
    como_formulario()    colunas -> dicionário no formato do formulário
"""

from datetime import date, datetime, time

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prontuario import (calcular_idade, classificar, fmt_data, fmt_reais, ler_data, ler_valor,
                        previsao_termino)
from validacao import fmt_cpf, fmt_hora, fmt_telefone, ler_hora, limpar_rg, so_digitos

db = SQLAlchemy()

# Legenda da aba Triagens: 1 ativo, 2 inativo, 3 em admissão, 4 lista de espera, 5 desistiu
STATUS = {
    "em_admissao": "Em processo de admissão",
    "lista_espera": "Lista de espera",
    "desistiu": "Desistência",
    "ativo": "Ativo",
    "inativo": "Inativo",
}
STATUS_TRIAGEM = ("em_admissao", "lista_espera", "desistiu")
STATUS_INTERNACAO = ("ativo", "inativo")
MODALIDADES = ["Presencial", "Online"]


class CamposDeFormulario:
    """Comportamento comum: copiar formulário <-> colunas, convertendo pelo tipo."""

    CAMPOS_DO_SISTEMA = {"id", "pessoa_id", "internacao_id", "status", "criado_em", "atualizado_em"}

    def preencher(self, form):
        for coluna in self.__table__.columns:
            # só mexe no que veio no formulário: o form de triagem não apaga
            # campos que só existem no prontuário, e vice-versa
            if coluna.name in self.CAMPOS_DO_SISTEMA or coluna.name not in form:
                continue
            bruto = (form.get(coluna.name) or "").strip()
            if isinstance(coluna.type, Date):
                valor = ler_data(bruto)
            elif isinstance(coluna.type, Time):
                valor = ler_hora(bruto)
            elif isinstance(coluna.type, Float):
                valor = ler_valor(bruto)
            else:
                # o Postgres recusa texto maior que a coluna (o SQLite aceitava): corta no limite
                valor = bruto[:coluna.type.length] if coluna.type.length else bruto
            setattr(self, coluna.name, valor)
        self.normalizar()

    def normalizar(self):
        pass

    def como_formulario(self):
        dados = {}
        for coluna in self.__table__.columns:
            if coluna.name in self.CAMPOS_DO_SISTEMA:
                continue
            valor = getattr(self, coluna.name)
            if valor is None:
                dados[coluna.name] = ""
            elif isinstance(coluna.type, Time):
                dados[coluna.name] = fmt_hora(valor)
            elif isinstance(valor, date):
                dados[coluna.name] = valor.isoformat()
            elif isinstance(valor, float):
                dados[coluna.name] = f"{valor:.2f}"
            else:
                dados[coluna.name] = str(valor)
        return dados


# =========================================================================
class Pessoa(CamposDeFormulario, db.Model):
    __tablename__ = "pessoas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    nascimento: Mapped[date | None] = mapped_column(Date)
    cpf: Mapped[str] = mapped_column(String(20), default="", index=True)
    rg: Mapped[str] = mapped_column(String(20), default="")
    cartao_sus: Mapped[str] = mapped_column(String(30), default="")
    estado_civil: Mapped[str] = mapped_column(String(20), default="")
    estado_civil_outro: Mapped[str] = mapped_column(String(50), default="")
    conjuge: Mapped[str] = mapped_column(String(200), default="")
    escolaridade: Mapped[str] = mapped_column(String(100), default="")
    religiao: Mapped[str] = mapped_column(String(100), default="")
    profissao: Mapped[str] = mapped_column(String(100), default="")
    mae: Mapped[str] = mapped_column(String(200), default="")
    # endereço
    cep: Mapped[str] = mapped_column(String(10), default="")
    endereco: Mapped[str] = mapped_column(String(200), default="")
    numero: Mapped[str] = mapped_column(String(20), default="")
    bairro: Mapped[str] = mapped_column(String(100), default="")
    cidade: Mapped[str] = mapped_column(String(100), default="")
    estado: Mapped[str] = mapped_column(String(2), default="")
    # contatos: 1 = família/responsável, 2 = outro, 3 = do próprio acolhido
    contato1: Mapped[str] = mapped_column(String(100), default="")
    contato2: Mapped[str] = mapped_column(String(100), default="")
    contato3: Mapped[str] = mapped_column(String(100), default="")

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now,
                                                    onupdate=datetime.now)

    internacoes: Mapped[list["Internacao"]] = relationship(
        back_populates="pessoa", order_by="Internacao.id")

    def normalizar(self):
        self.cpf = so_digitos(self.cpf)
        self.rg = limpar_rg(self.rg)
        self.cep = so_digitos(self.cep)
        self.estado = (self.estado or "").upper()[:2]
        for campo in ("contato1", "contato2", "contato3"):
            setattr(self, campo, fmt_telefone(getattr(self, campo)))

    @property
    def ultima_internacao(self):
        """A mais recente pela data (internação, ou 1º contato se for só triagem)."""
        if not self.internacoes:
            return None
        return max(self.internacoes,
                   key=lambda i: (i.inicio or i.internacao_agendada or i.primeiro_contato or date.min, i.id))

    def resumo(self):
        """Usado na busca de 'paciente existente'."""
        ultima = self.ultima_internacao
        return {
            "id": self.id,
            "nome": self.nome,
            "cpf": fmt_cpf(self.cpf),
            "nascimento": fmt_data(self.nascimento),
            "cidade": "/".join(p for p in (self.cidade, self.estado) if p),
            "ultima": (f"{STATUS[ultima.status]}"
                       + (f" desde {fmt_data(ultima.inicio)}" if ultima.inicio else ""))
                      if ultima else "",
        }


# =========================================================================
class Internacao(CamposDeFormulario, db.Model):
    __tablename__ = "internacoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    pessoa_id: Mapped[int] = mapped_column(ForeignKey("pessoas.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="em_admissao", index=True)

    # --- triagem
    primeiro_contato: Mapped[date | None] = mapped_column(Date)
    hora_primeiro_contato: Mapped[time | None] = mapped_column(Time)
    data_triagem: Mapped[date | None] = mapped_column(Date)
    hora_triagem: Mapped[time | None] = mapped_column(Time)
    modalidade: Mapped[str] = mapped_column(String(20), default="")
    # dia marcado para internar (pode não acontecer: desistência)
    internacao_agendada: Mapped[date | None] = mapped_column(Date)
    hora_agendada: Mapped[time | None] = mapped_column(Time)

    # --- internação (efetiva: o dia em que ele de fato entrou na casa)
    inicio: Mapped[date | None] = mapped_column(Date)
    hora_internacao: Mapped[time | None] = mapped_column(Time)
    tratamento_ate: Mapped[date | None] = mapped_column(Date)
    data_documento: Mapped[date | None] = mapped_column(Date)
    termino: Mapped[date | None] = mapped_column(Date)
    motivo: Mapped[str] = mapped_column(String(20), default="")

    # --- responsável (pode mudar de uma internação para outra)
    resp_nome: Mapped[str] = mapped_column(String(200), default="")
    parentesco: Mapped[str] = mapped_column(String(50), default="")
    resp_rg: Mapped[str] = mapped_column(String(20), default="")
    resp_cpf: Mapped[str] = mapped_column(String(20), default="")

    # --- contribuição
    convenio: Mapped[str] = mapped_column(String(50), default="")
    contribuicao_valor: Mapped[float] = mapped_column(Float, default=0.0)
    contribuicao_condicoes: Mapped[str] = mapped_column(String(200), default="")

    # --- documentos entregues
    doc_rg: Mapped[str] = mapped_column(String(20), default="")
    doc_cnh: Mapped[str] = mapped_column(String(20), default="")
    doc_cin: Mapped[str] = mapped_column(String(20), default="")
    doc_sus: Mapped[str] = mapped_column(String(20), default="")
    doc_ctps: Mapped[str] = mapped_column(String(20), default="")
    doc_outro: Mapped[str] = mapped_column(String(100), default="")

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now,
                                                    onupdate=datetime.now)

    pessoa: Mapped[Pessoa] = relationship(back_populates="internacoes")
    parcelas: Mapped[list["Parcela"]] = relationship(
        back_populates="internacao", order_by="Parcela.numero", cascade="all, delete-orphan")

    def normalizar(self):
        self.resp_cpf = so_digitos(self.resp_cpf)
        self.resp_rg = limpar_rg(self.resp_rg)
        # grava o valor já com a regra aplicada (CAPS AD / Tarumã = 0,00)
        self.contribuicao_valor, _ = classificar(self.convenio, self.contribuicao_valor or 0.0)

    # ------------------------------------------------------------ leitura
    @property
    def e_triagem(self):
        return self.status in STATUS_TRIAGEM

    @property
    def status_txt(self):
        txt = STATUS.get(self.status, self.status)
        return f"{txt} ({self.motivo})" if self.status == "inativo" and self.motivo else txt

    @property
    def convenio_txt(self):
        return classificar(self.convenio, self.contribuicao_valor or 0.0)[1]

    def dados_completos(self):
        """Pessoa + internação no formato do formulário (para o .docx e para editar)."""
        return {**self.pessoa.como_formulario(), **self.como_formulario()}

    def _comum(self):
        p = self.pessoa
        iso = lambda d: d.isoformat() if d else ""
        return {
            "id": self.id,
            "pessoa_id": p.id,
            "nome": p.nome,
            "cpf": fmt_cpf(p.cpf),
            "idade": calcular_idade(p.nascimento, date.today()),
            "convenio": self.convenio_txt,
            "inicio": iso(self.inicio), "inicio_fmt": fmt_data(self.inicio),
            "responsavel": self.resp_nome,
            "parentesco": self.parentesco,
            "contato": p.contato1 or p.contato2 or p.contato3,
            "status": self.status,
            "status_txt": self.status_txt,
        }

    def para_lista(self):
        """Linha da lista de internos."""
        previsao = previsao_termino(self.inicio, self.tratamento_ate)
        return {**self._comum(),
                "valor": self.contribuicao_valor,
                "valor_fmt": fmt_reais(self.contribuicao_valor or 0.0),
                "previsao": previsao.isoformat() if previsao else "",
                "previsao_fmt": fmt_data(previsao),
                "termino": self.termino.isoformat() if self.termino else "",
                "termino_fmt": fmt_data(self.termino),
                "parcelas": len(self.parcelas)}

    def para_triagem(self):
        """Linha da lista de triagens."""
        iso = lambda d: d.isoformat() if d else ""
        triagem = " ".join(p for p in (fmt_data(self.data_triagem), fmt_hora(self.hora_triagem)) if p)
        agendada = " ".join(p for p in (fmt_data(self.internacao_agendada), fmt_hora(self.hora_agendada)) if p)
        return {**self._comum(),
                "primeiro_contato": iso(self.primeiro_contato),
                "primeiro_contato_fmt": fmt_data(self.primeiro_contato),
                "triagem": iso(self.data_triagem),
                "triagem_fmt": triagem + (f" · {self.modalidade}" if self.modalidade else ""),
                "agendada": iso(self.internacao_agendada),
                "agendada_fmt": agendada,
                "hora_agendada": fmt_hora(self.hora_agendada),
                "convenio_definido": self.convenio not in ("", "A definir")}


# =========================================================================
class Parcela(db.Model):
    __tablename__ = "parcelas"

    id: Mapped[int] = mapped_column(primary_key=True)
    internacao_id: Mapped[int] = mapped_column(ForeignKey("internacoes.id"), index=True)
    numero: Mapped[int] = mapped_column()
    data: Mapped[date | None] = mapped_column(Date)
    valor: Mapped[float | None] = mapped_column(Float)

    internacao: Mapped[Internacao] = relationship(back_populates="parcelas")


# =========================================================================
class AvisoDispensado(db.Model):
    """Avisos que alguém marcou como 'ciente' no quadro da home."""
    __tablename__ = "avisos_dispensados"

    chave: Mapped[str] = mapped_column(String(200), primary_key=True)
    dispensado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# =========================================================================
class Usuario(db.Model):
    """Quem pode entrar no sistema. A senha nunca é gravada: só o hash dela."""
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), unique=True)  # sempre em minúsculas
    senha_hash: Mapped[str] = mapped_column(String(256))
    ativo: Mapped[bool] = mapped_column(default=True)
    # proteção contra tentativa e erro: após várias senhas erradas, bloqueia por um tempo
    falhas: Mapped[int] = mapped_column(default=0)
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
