"""
Banco de dados (SQLite via Flask-SQLAlchemy).

Tabelas dos acolhidos:

    pessoas      quem é o acolhido (dados que não mudam de uma internação para outra)
       │ 1
       │ N
    internacoes  cada passagem pela casa: começa como triagem (em admissão, lista de
       │ 1       espera, desistência) e, ao ser admitida, vira internação (ativo/inativo).
       │ N       Responsável, convênio e datas ficam aqui — mudam a cada internação.
    parcelas     contribuições pagas naquela internação (nº, data, valor)
    relatorios_sociais  o acolhimento social daquela internação: ficha, relatório e parecer (1 por internação)
    adendos_sociais     correções acrescentadas a um acolhimento social já finalizado

Os nomes das colunas são os mesmos dos campos dos formulários (name="..."):
    preencher(form)      formulário -> colunas (só os campos que vieram no form)
    como_formulario()    colunas -> dicionário no formato do formulário
"""

from datetime import date, datetime, time

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prontuario import (calcular_idade, categoria_efetiva, classificar, fmt_data, fmt_reais, ler_data,
                        ler_valor, previsao_termino, tipo_da_categoria)
from servico_social import estado
from validacao import fmt_cpf, fmt_hora, fmt_telefone, ler_hora, limpar_rg, so_digitos

db = SQLAlchemy()

# Legenda da aba Triagens: 1 ativo, 2 inativo, 3 em admissão, 4 lista de espera, 5 desistiu
# (rejeitado = a triagem concluiu que o tratamento da casa não é o que a pessoa precisa; o porquê é o parecer da assistente social)
STATUS = {
    "em_admissao": "Em processo de admissão",
    "lista_espera": "Lista de espera",
    "desistiu": "Desistência",
    "rejeitado": "Rejeitado na triagem",
    "ativo": "Ativo",
    "inativo": "Inativo",
}
STATUS_TRIAGEM = ("em_admissao", "lista_espera", "desistiu", "rejeitado")
STATUS_INTERNACAO = ("ativo", "inativo")
MODALIDADES = ["Presencial", "Online"]

# Onde está o prontuário em papel (o envelope com os termos de compromisso) de quem recebeu baixa.
# Ele vai para a casa de acolhida com o interno e precisa voltar ao escritório para o relatório de saída.
# "" = sem controle (baixas anteriores a este recurso, que não geram aviso).
ENVELOPE_PENDENTE = "pendente"     # ainda na casa de acolhida
ENVELOPE_RECEBIDO = "recebido"     # de volta ao escritório


class CamposDeFormulario:
    """Comportamento comum: copiar formulário <-> colunas, convertendo pelo tipo."""

    CAMPOS_DO_SISTEMA = {"id", "pessoa_id", "internacao_id", "status", "criado_em", "atualizado_em",
                         "envelope", "envelope_recebido_em", "excluido_em", "excluido_por", "exames_impressos_para"}

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
    # excluída (exclusao.py): some das telas e das buscas, mas continua no banco até o administrador apagar de vez
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime)

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
    # --- envelope do prontuário depois da baixa (ENVELOPE_PENDENTE / ENVELOPE_RECEBIDO, ou "")
    envelope: Mapped[str] = mapped_column(String(10), default="")
    envelope_recebido_em: Mapped[date | None] = mapped_column(Date)

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

    # --- pedido de exames e enxoval: a data de internação para a qual já foram impressos (None = ainda não)
    exames_impressos_para: Mapped[date | None] = mapped_column(Date)

    # --- exclusão em duas etapas (exclusao.py): quem não é administrador só "exclui" (some das telas, fica no banco);
    # o administrador vê o que foi excluído e apaga de vez
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime)
    excluido_por: Mapped[str] = mapped_column(String(50), default="")

    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now,
                                                    onupdate=datetime.now)

    pessoa: Mapped[Pessoa] = relationship(back_populates="internacoes")
    parcelas: Mapped[list["Parcela"]] = relationship(
        back_populates="internacao", order_by="Parcela.numero", cascade="all, delete-orphan")
    relatorio_social: Mapped["RelatorioSocial | None"] = relationship(
        back_populates="internacao", uselist=False, cascade="all, delete-orphan")

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
        """Texto completo da linha de convênio, como vai para o Word: "Particular — Social Parcial II"."""
        return classificar(self.convenio, self.contribuicao_valor or 0.0)[1]

    @property
    def categoria(self):
        """Só a categoria efetiva, como aparece nas telas: CAPS AD, Prefeitura Tarumã, Social,
        Social I, Social II, Particular (ou "A definir")."""
        return categoria_efetiva(self.convenio, self.contribuicao_valor or 0.0)

    @property
    def categoria_tipo(self):
        """Classe de cor da categoria (a mesma em todas as telas)."""
        return tipo_da_categoria(self.categoria)

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
            "convenio": self.convenio_txt,      # texto completo (a busca ainda acha "particular")
            "categoria": self.categoria,        # o que as listas mostram
            "categoria_tipo": self.categoria_tipo,
            "inicio": iso(self.inicio), "inicio_fmt": fmt_data(self.inicio),
            "responsavel": self.resp_nome,
            "parentesco": self.parentesco,
            "contato": p.contato1 or p.contato2 or p.contato3,
            "status": self.status,
            "status_txt": self.status_txt,
            "acolhimento": estado(self.relatorio_social),     # acolhimento social: "" (não iniciado) | rascunho | finalizado
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
class RelatorioSocial(db.Model):
    """O acolhimento social de uma internação (servico_social.py): a ficha, o relatório livre, a classificação de risco e
    o parecer. Só as respostas que foram digitadas, num JSON {campo: texto}. Uma linha por internação; mora aqui, não em
    colunas, porque o modelo do escritório pode mudar.

    Nasce como rascunho, que a assistente social edita à vontade. Finalizar trava: fica a data, a hora e a assinatura
    (nome, cargo e registro profissional de quem finalizou, como estavam naquele momento) e as correções passam a ser
    adendos (AdendoSocial)."""
    __tablename__ = "relatorios_sociais"

    id: Mapped[int] = mapped_column(primary_key=True)
    internacao_id: Mapped[int] = mapped_column(ForeignKey("internacoes.id"), unique=True)
    dados: Mapped[dict] = mapped_column(JSON, default=dict)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    atualizado_por: Mapped[str] = mapped_column(String(50), default="")      # o usuário que salvou por último
    situacao: Mapped[str] = mapped_column(String(12), default="rascunho")    # rascunho | finalizado
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime)
    finalizado_por: Mapped[str] = mapped_column(String(50), default="")      # o usuário (login) que finalizou
    assinatura: Mapped[str] = mapped_column(String(200), default="")         # "Nome — cargo — registro", como estava ao finalizar

    internacao: Mapped[Internacao] = relationship(back_populates="relatorio_social")
    adendos: Mapped[list["AdendoSocial"]] = relationship(
        back_populates="relatorio", order_by="AdendoSocial.id", cascade="all, delete-orphan")

    @property
    def finalizado(self):
        return self.situacao == "finalizado"


# =========================================================================
class AdendoSocial(db.Model):
    """Correção ou informação nova acrescentada a um acolhimento social já finalizado. Nunca se edita nem se apaga:
    o documento finalizado fica como foi assinado e os adendos vêm depois dele, cada um com data, hora e autor."""
    __tablename__ = "adendos_sociais"

    id: Mapped[int] = mapped_column(primary_key=True)
    relatorio_id: Mapped[int] = mapped_column(ForeignKey("relatorios_sociais.id"), index=True)
    texto: Mapped[str] = mapped_column(String(3000))
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    criado_por: Mapped[str] = mapped_column(String(200), default="")         # "Nome — cargo — registro" de quem escreveu

    relatorio: Mapped[RelatorioSocial] = relationship(back_populates="adendos")


# =========================================================================
class CodigoSeguranca(db.Model):
    """Códigos de uso único que a pessoa recebe por e-mail (contas.py): o de 6 dígitos que confirma o e-mail e o link do "esqueci
    minha senha". Só o resumo (sha256) do código é guardado: quem lê o banco não consegue usá-lo."""
    __tablename__ = "codigos_seguranca"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(index=True)
    finalidade: Mapped[str] = mapped_column(String(10), index=True)                # "email" ou "senha"
    resumo: Mapped[str] = mapped_column(String(64), index=True)
    destino: Mapped[str] = mapped_column(String(120), default="")                  # para qual e-mail foi enviado
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    expira_em: Mapped[datetime] = mapped_column(DateTime)
    usado_em: Mapped[datetime | None] = mapped_column(DateTime)
    tentativas: Mapped[int] = mapped_column(default=0)


# =========================================================================
class Evento(db.Model):
    """Trilha de auditoria (auditoria.py): quem fez o quê, em qual registro e quando. Só se acrescenta: nenhuma tela edita nem
    apaga. Não guarda o conteúdo dos dados (só QUAIS campos mudaram) e não aponta para as outras tabelas por chave: sobrevive
    a um 'apagar de vez' e não vira uma segunda cópia dos dados sensíveis."""
    __tablename__ = "eventos_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    quando: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    usuario: Mapped[str] = mapped_column(String(50), default="", index=True)       # o login (vazio: ninguém entrou, ou usuário que não existe)
    acao: Mapped[str] = mapped_column(String(40), index=True)                      # o código (auditoria.ACOES)
    categoria: Mapped[str] = mapped_column(String(15), index=True)                 # entrada, leitura, alteracao, administracao ou negado
    alvo_tipo: Mapped[str] = mapped_column(String(20), default="")                 # internacao, funcionario, nivel...
    alvo_id: Mapped[int | None] = mapped_column()
    pessoa_id: Mapped[int | None] = mapped_column(index=True)                      # o acolhido, para "tudo o que mexeu nesta pessoa"
    detalhe: Mapped[str] = mapped_column(String(300), default="")
    endereco: Mapped[str] = mapped_column(String(45), default="")                  # o endereço de rede do computador
    navegador: Mapped[str] = mapped_column(String(120), default="")


# =========================================================================
class AvisoDispensado(db.Model):
    """Avisos que alguém marcou como 'ciente' no quadro da home."""
    __tablename__ = "avisos_dispensados"

    chave: Mapped[str] = mapped_column(String(200), primary_key=True)
    dispensado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# =========================================================================
class Convenio(db.Model):
    """Convênios do cadastro (Cadastros > Convênios). Veja catalogo.py: é de lá que o resto do sistema os lê."""
    __tablename__ = "convenios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), unique=True)     # o texto guardado em cada internação: não muda
    nome_tela: Mapped[str] = mapped_column(String(50))            # como aparece nas telas
    slug: Mapped[str] = mapped_column(String(60), unique=True)    # endereço do relatório do convênio
    gratuito: Mapped[bool] = mapped_column(default=True)          # contribuição sempre R$ 0,00 (o Particular não é)
    vagas: Mapped[int | None] = mapped_column()                   # limite de vagas; vazio = não definido
    cor: Mapped[str] = mapped_column(String(20), default="outro")
    ativo: Mapped[bool] = mapped_column(default=True)             # desativado: não aparece para escolher, o histórico fica
    ordem: Mapped[int] = mapped_column(default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class NivelAcesso(db.Model):
    """Níveis de acesso (Cadastros > Níveis de acesso), em cascata: o de `ordem` menor tem mais acesso e inclui tudo o que
    os de baixo têm. O que cada nível pode fazer fica em PermissaoNivel (veja permissoes.py)."""
    __tablename__ = "niveis_acesso"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(50), unique=True)
    descricao: Mapped[str] = mapped_column(String(200), default="")
    ordem: Mapped[int] = mapped_column(default=0)                 # 1 = o que tem mais acesso
    ativo: Mapped[bool] = mapped_column(default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class PermissaoNivel(db.Model):
    """O nível mínimo de cada permissão (Cadastros > Permissões): quem está nesse nível, ou acima dele na cascata, pode.
    Uma linha por permissão configurável (a lista está em permissoes.py); a que não tem linha cai no padrão de fábrica."""
    __tablename__ = "permissoes_nivel"

    chave: Mapped[str] = mapped_column(String(40), primary_key=True)
    nivel_id: Mapped[int] = mapped_column(ForeignKey("niveis_acesso.id"))
    alterado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    alterado_por: Mapped[str] = mapped_column(String(50), default="")

    nivel: Mapped[NivelAcesso] = relationship()


class Funcionario(db.Model):
    """Quem trabalha no escritório (Cadastros > Funcionários): assina como responsável pela emissão dos documentos."""
    __tablename__ = "funcionarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    cargo: Mapped[str] = mapped_column(String(100), default="")
    ativo: Mapped[bool] = mapped_column(default=True)
    padrao: Mapped[bool] = mapped_column(default=False)           # assina quando ninguém escolhe (só um por vez)
    usuario: Mapped[str] = mapped_column(String(50), default="")  # login desta pessoa: os documentos que ela emite saem no nome dela
    nivel_id: Mapped[int | None] = mapped_column(ForeignKey("niveis_acesso.id"), index=True)
    # Serviço Social: lê e escreve o acolhimento social (ficha, relatório e parecer), que é sigiloso, e assina com o
    # registro profissional (CRESS). O administrador também tem acesso, sem precisar desta marca.
    servico_social: Mapped[bool] = mapped_column(default=False)
    registro_profissional: Mapped[str] = mapped_column(String(30), default="")
    # e-mail institucional (só o administrador altera): serve para o "esqueci minha senha" e para os avisos de segurança, e só vale
    # depois de confirmado com um código enviado a ele (contas.py)
    email: Mapped[str] = mapped_column(String(120), default="")
    email_confirmado_em: Mapped[datetime | None] = mapped_column(DateTime)
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    nivel: Mapped[NivelAcesso | None] = relationship()


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
    # senha que o administrador definiu: a pessoa tem de trocá-la antes de usar qualquer outra tela
    trocar_senha: Mapped[bool] = mapped_column(default=False)
    # segundo fator (aplicativo autenticador no celular, TOTP; totp.py). O segredo fica CIFRADO com uma chave que não vai no banco
    # (instance/secret.key), para um backup do banco sozinho não bastar. `totp_ativo` só vale depois de a pessoa digitar um código
    # que o aplicativo gerou (até lá o segredo é só de uma ativação pendente).
    totp_segredo: Mapped[str] = mapped_column(String(200), default="")
    totp_ativo: Mapped[bool] = mapped_column(default=False)
    totp_ultimo_passo: Mapped[int] = mapped_column(default=0)                      # o último código aceito: um código só vale uma vez
    totp_recuperacao: Mapped[str] = mapped_column(String(2000), default="")        # resumos (scrypt) dos códigos de recuperação que ainda não foram usados
    criado_em: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
