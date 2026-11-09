"""
Importa para o sistema as pessoas de pastas e planilhas antigas (ex-residentes), a partir de uma LISTA revisada por você.

    python importar_historico.py LISTA.xlsx                  só SIMULA: mostra o que faria e grava o relatório; não muda nada no banco
    python importar_historico.py LISTA.xlsx --gravar         faz o backup, mostra o resumo, pede que você digite SIM e grava
    python importar_historico.py --desfazer LOTE             simula desfazer um lote já importado (LOTE está no relatório e na ficha)
    python importar_historico.py --desfazer LOTE --gravar    apaga de vez o que o lote criou e ninguém mexeu depois (os outros ficam e são listados)

Outras opções: --relatorio ARQ.csv (onde guardar o relatório), --usuario NOME (quem aparece na trilha de auditoria),
--sem-backup (só para testes), --sim (não pergunta; para scripts), --pular-erros (grava o que está certo mesmo havendo linhas com erro).

A LISTA é uma planilha (.xlsx) ou CSV com UMA LINHA POR INTERNAÇÃO e estas colunas (a ordem não importa; só Nome é obrigatória):

    Nome | CPF | Nascimento | Cidade | Estado | Convênio | Entrada | Saída | Motivo | Origem | Forçar

  * Linhas com o mesmo CPF (ou, sem CPF, o mesmo nome) são UMA pessoa com várias internações.
  * Datas: dd/mm/aaaa, aaaa-mm-dd ou data do Excel. Vazio, "-" e "Não informado" valem como "sem data": nada é inventado.
  * CPF que não confere pelo dígito verificador entra em branco (e vai para o relatório como aviso).
  * Convênio: Particular, CAPS AD, Prefeitura Tarumã (ou os nomes do Cadastros). Não reconhecido ou vazio fica em branco ("A definir").
  * Motivo: Conclusão, Desistência ou Desligamento. "Exclusão" vira Desligamento. Outros (Falecimento, Não informado) ficam em branco.
  * Origem: de onde veio (por exemplo "Ex-Residentes / Saíram em 2024"); aparece na ficha como "Registro importado".
  * Forçar = "sim": cria mesmo que já exista alguém com o mesmo NOME no sistema (use só se for outra pessoa mesmo).

O que o script faz, e o que NÃO faz:
  * Cada internação entra como INATIVA, sem baixa, sem envelope e sem notificação para ninguém. Nenhuma data é inventada.
  * Quem já está no sistema NÃO é alterado nem duplicado: a linha é pulada e aparece no relatório (pelo CPF, ou pelo nome igual, inclusive na lixeira).
  * Linha com erro (data ilegível, saída antes da entrada, sem nome) não entra; com erros o script não grava, a menos que use --pular-erros.
  * A gravação é uma transação só: ou entra tudo, ou nada. Antes dela o banco ganha uma cópia de backup (a mesma do backup do dia).
  * Fica um registro na trilha de auditoria (importacao.lote) e o número do lote em cada registro (origem = "... | lote AAAAMMDD-HHMMSS").
"""

import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from app import app
import auditoria
import backup
import exclusao
from modelos import Internacao, Pessoa, db
from validacao import cpf_valido, escrever_bem, fmt_cpf, so_digitos

RAIZ = Path(__file__).resolve().parent
ORIGEM_PADRAO = "Lista de importação"

# ---- o que a lista pode trazer, e como vira o que o sistema entende (mude aqui se a casa preferir outro jeito)
MOTIVOS = {"conclusao": "Conclusão", "desistencia": "Desistência", "desligamento": "Desligamento",
           "exclusao": "Desligamento"}                      # a planilha antiga usava "Exclusão" para quem foi desligado
AVISO_DO_MOTIVO = {"exclusao": "motivo \"Exclusão\" registrado como Desligamento"}
CONVENIOS = {"particular": "Particular", "caps ad": "CAPS AD", "capsad": "CAPS AD", "convenio taruma": "Prefeitura Tarumã", "taruma": "Prefeitura Tarumã",
             "prefeitura taruma": "Prefeitura Tarumã", "social": "Particular"}        # "Social" é Particular com contribuição R$ 0,00 (a categoria sai do valor)
SEM_DADO = {"", "-", "—", "nao informado", "n/i", "ni", "indefinido", "nao consta"}
CABECALHOS = {"nome": "nome", "cpf": "cpf", "nascimento": "nascimento", "data de nascimento": "nascimento", "cidade": "cidade", "estado": "estado", "uf": "estado",
              "convenio": "convenio", "entrada": "entrada", "saida": "saida", "motivo": "motivo", "origem": "origem", "forcar": "forcar"}


# ------------------------------------------------------------------ texto e datas
def sem_acento(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "")) if unicodedata.category(c) != "Mn")


def norm(t):
    """Para comparar: sem acento, sem maiúsculas, sem pontuação, sem espaço sobrando."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", sem_acento(t).lower())).strip()


def ler_data_da_lista(v):
    """(data, erro). Vazio e 'Não informado' = sem data (sem erro)."""
    if v is None:
        return None, None
    if isinstance(v, datetime):
        return v.date(), None
    if isinstance(v, date):
        return v, None
    t = str(v).strip()
    if norm(t) in SEM_DADO:
        return None, None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", t)
    if m:
        ano, mes, dia = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
        if not m:
            return None, f"data ilegível: \"{t}\" (use dd/mm/aaaa)"
        dia, mes, ano = (int(x) for x in m.groups())
    try:
        return date(ano, mes, dia), None
    except ValueError:
        return None, f"data que não existe: \"{t}\""


def ler_cpf(v):
    """(cpf só com dígitos ou '', aviso). O Excel apaga zeros à esquerda: completa com zeros se o dígito conferir."""
    if isinstance(v, float) and v.is_integer():          # célula numérica do Excel (12345678909.0): sem o ".0", senão o dígito a mais estraga o CPF
        v = int(v)
    d = so_digitos("" if v is None else str(v))
    if not d:
        return "", None
    if len(d) < 11 and cpf_valido(d.zfill(11)):
        d = d.zfill(11)
    if len(d) == 11 and cpf_valido(d):
        return d, None
    return "", f"CPF {v} não confere (dígito verificador): entrou sem CPF"


# ------------------------------------------------------------------ a lista
@dataclass
class Linha:
    n: int
    nome: str = ""
    cpf: str = ""
    nascimento: date | None = None
    cidade: str = ""
    estado: str = ""
    convenio: str = ""
    entrada: date | None = None
    saida: date | None = None
    motivo: str = ""
    origem: str = ""
    forcar: bool = False
    avisos: list = field(default_factory=list)
    erros: list = field(default_factory=list)
    resultado: str = ""            # criar | pular | recusar
    detalhe: str = ""

    @property
    def chave(self):
        return self.cpf or "n:" + norm(self.nome)


def _linhas_do_arquivo(caminho):
    """[(número da linha, {coluna: valor})], com as colunas já reconhecidas."""
    caminho = Path(caminho)
    if not caminho.is_file():
        sys.exit(f"Não achei a lista: {caminho}")
    if caminho.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            sys.exit("Para ler .xlsx falta o pacote openpyxl (pip install openpyxl). Ou salve a lista como CSV.")
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        ws = wb["Importar"] if "Importar" in wb.sheetnames else wb.worksheets[0]
        linhas = list(ws.iter_rows(values_only=True))
    else:
        bruto = caminho.read_bytes()
        try:
            texto = bruto.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = bruto.decode("cp1252")
        amostra = texto[:2000]
        delimitador = ";" if amostra.count(";") >= amostra.count(",") else ","
        linhas = list(csv.reader(texto.splitlines(), delimiter=delimitador))
    if not linhas:
        sys.exit("A lista está vazia.")
    colunas = {}
    for i, titulo in enumerate(linhas[0]):
        chave = CABECALHOS.get(norm(titulo))
        if chave and chave not in colunas:
            colunas[chave] = i
    if "nome" not in colunas:
        sys.exit("A lista precisa ter a coluna \"Nome\" na primeira linha.")
    resultado = []
    for n, r in enumerate(linhas[1:], 2):
        valores = {k: (r[i] if i < len(r) else None) for k, i in colunas.items()}
        if any(str(v).strip() for v in valores.values() if v is not None):
            resultado.append((n, valores))
    return resultado


def ler_lista(caminho, cat, hoje=None):
    """As linhas da lista, já conferidas uma a uma (o que dá para saber sem olhar o banco)."""
    hoje = hoje or date.today()
    linhas = []
    for n, v in _linhas_do_arquivo(caminho):
        L = Linha(n=n)
        L.nome = escrever_bem("nome", str(v.get("nome") or "").strip())
        if not L.nome:
            L.erros.append("sem nome")
        L.cpf, aviso = ler_cpf(v.get("cpf"))
        if aviso:
            L.avisos.append(aviso)
        L.nascimento, erro = ler_data_da_lista(v.get("nascimento"))
        if erro:
            L.avisos.append("nascimento: " + erro + " (ficou em branco)")
            L.nascimento = None
        elif L.nascimento and not (date(1900, 1, 1) <= L.nascimento <= hoje):
            L.avisos.append(f"nascimento {L.nascimento:%d/%m/%Y} fora do possível (ficou em branco)")
            L.nascimento = None
        L.cidade = escrever_bem("local", str(v.get("cidade") or "").strip())
        uf = str(v.get("estado") or "").strip().upper()
        L.estado = uf if re.fullmatch(r"[A-Z]{2}", uf) else ""
        # convênio
        bruto = str(v.get("convenio") or "").strip()
        if norm(bruto) not in SEM_DADO:
            nome = next((c.nome for c in cat.convenios if norm(c.nome) == norm(bruto) or norm(c.nome_tela) == norm(bruto)), None) or CONVENIOS.get(norm(bruto))
            if nome and cat.existe(nome):
                L.convenio = nome
            else:
                L.avisos.append(f"convênio \"{bruto}\" não existe no sistema: ficou em branco (A definir)")
        # datas
        L.entrada, erro = ler_data_da_lista(v.get("entrada"))
        if erro:
            L.erros.append("entrada: " + erro)
        L.saida, erro = ler_data_da_lista(v.get("saida"))
        if erro:
            L.erros.append("saída: " + erro)
        if L.entrada and L.entrada > hoje:
            L.erros.append(f"entrada no futuro ({L.entrada:%d/%m/%Y})")
        if L.saida and L.saida > hoje:
            L.erros.append(f"saída no futuro ({L.saida:%d/%m/%Y})")
        if L.entrada and L.saida and L.saida < L.entrada:
            L.erros.append(f"saída ({L.saida:%d/%m/%Y}) antes da entrada ({L.entrada:%d/%m/%Y})")
        # motivo
        bruto = str(v.get("motivo") or "").strip()
        if norm(bruto) not in SEM_DADO:
            if norm(bruto) in MOTIVOS:
                L.motivo = MOTIVOS[norm(bruto)]
                if norm(bruto) in AVISO_DO_MOTIVO:
                    L.avisos.append(AVISO_DO_MOTIVO[norm(bruto)])
            else:
                L.avisos.append(f"motivo \"{bruto}\" não tem equivalente no sistema: ficou em branco")
        L.origem = re.sub(r"\s+", " ", str(v.get("origem") or "").strip())[:100] or ORIGEM_PADRAO
        L.forcar = norm(v.get("forcar")) in ("sim", "s", "1", "x")
        linhas.append(L)
    return linhas


# ------------------------------------------------------------------ o que já está no sistema
def pessoas_do_sistema():
    """({CPF: (nome, na lixeira, já importada)}, {nome normalizado: (nome, na lixeira, já importada)}), inclusive o que está na lixeira."""
    with exclusao.vendo_tudo():
        importadas = set(db.session.execute(db.select(Internacao.pessoa_id).filter(Internacao.origem != "")).scalars())
        itens = db.session.execute(db.select(Pessoa.id, Pessoa.nome, Pessoa.cpf, Pessoa.excluido_em)).all()
    por_cpf, por_nome = {}, {}
    for id_, nome, cpf, excluida in itens:
        registro = (nome, bool(excluida), id_ in importadas)
        c = so_digitos(cpf)
        if len(c) == 11:
            por_cpf.setdefault(c, registro)
        anterior = por_nome.get(norm(nome))
        # com vários de mesmo nome, basta UM ter sido importado para a lista não criar de novo (é o que faz repetir a importação não duplicar)
        por_nome[norm(nome)] = (anterior[0], anterior[1], anterior[2] or registro[2]) if anterior else registro
    return por_cpf, por_nome


def decidir(linhas, por_cpf, por_nome):
    """Marca cada linha: criar, pular (já existe) ou recusar (erro). Devolve os grupos (uma pessoa = um grupo) das linhas a criar."""
    grupos = {}
    for L in linhas:
        if L.erros:
            L.resultado, L.detalhe = "recusar", "; ".join(L.erros)
        else:
            grupos.setdefault(L.chave, []).append(L)
    criar = []
    nomes_com_cpf = {norm(L.nome): L for L in linhas if L.cpf and not L.erros}
    for chave, ls in grupos.items():
        primeira = ls[0]
        existente = por_cpf.get(primeira.cpf) if primeira.cpf else None
        motivo_do_pulo = None
        if existente:
            motivo_do_pulo = f"já está no sistema pelo CPF ({existente[0]}{', na lixeira' if existente[1] else ''})"
        elif norm(primeira.nome) in por_nome and (not any(L.forcar for L in ls) or por_nome[norm(primeira.nome)][2]):
            nome_s, lixeira, ja_importada = por_nome[norm(primeira.nome)]
            motivo_do_pulo = (f"já foi importada antes ({nome_s}{', na lixeira' if lixeira else ''})" if ja_importada else
                              f"já existe no sistema alguém com este nome ({nome_s}{', na lixeira' if lixeira else ''}): confira; se for outra pessoa, "
                              "ponha sim na coluna Forçar")
        if motivo_do_pulo:
            for L in ls:
                L.resultado, L.detalhe = "pular", motivo_do_pulo
            continue
        # a mesma pessoa pode vir com e sem CPF em linhas diferentes: não junto sozinho, aviso
        if not primeira.cpf and norm(primeira.nome) in nomes_com_cpf:
            for L in ls:
                L.avisos.append("há outra linha com este mesmo nome e com CPF: confira se não é a mesma pessoa (entrou como pessoa separada)")
        # campos da pessoa: o primeiro valor que aparecer; divergência vira aviso
        dados = {}
        for campo in ("cpf", "nascimento", "cidade", "estado"):
            valores = [getattr(L, campo) for L in ls if getattr(L, campo)]
            dados[campo] = valores[0] if valores else ("" if campo != "nascimento" else None)
            if len(set(valores)) > 1:
                for L in ls:
                    L.avisos.append(f"{campo} diferente entre as linhas desta pessoa: valeu o da primeira")
        for L in ls:
            L.resultado = "criar"
        criar.append({"nome": primeira.nome, "dados": dados, "linhas": sorted(ls, key=lambda L: (L.entrada or date.min, L.n))})
    return criar


# ------------------------------------------------------------------ gravar
def gravar(criar, lote):
    """Cria tudo numa transação só. Devolve (pessoas criadas, internações criadas)."""
    n_pessoas = n_internacoes = 0
    try:
        for g in criar:
            pessoa = Pessoa()
            db.session.add(pessoa)
            d = g["dados"]
            pessoa.preencher({"nome": g["nome"], "cpf": d["cpf"], "nascimento": d["nascimento"].isoformat() if d["nascimento"] else "",
                              "cidade": d["cidade"], "estado": d["estado"]})
            n_pessoas += 1
            for L in g["linhas"]:
                internacao = Internacao(pessoa=pessoa, status="inativo")
                db.session.add(internacao)
                iso = lambda x: x.isoformat() if x else ""
                internacao.preencher({"inicio": iso(L.entrada), "data_documento": iso(L.entrada), "termino": iso(L.saida), "motivo": L.motivo, "convenio": L.convenio})
                internacao.status = "inativo"
                internacao.origem = f"{L.origem} | lote {lote}"
                n_internacoes += 1
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return n_pessoas, n_internacoes


def fazer_backup():
    if db.engine.url.get_backend_name() != "sqlite":
        sys.exit("O backup automático é só para o SQLite. Faça o backup do banco por fora e use --sem-backup.")
    try:
        arquivo = backup.fazer_backup(Path(db.engine.url.database), backup.pasta_de_backup(None), 30)
    except backup.ErroDeBackup as erro:
        sys.exit(f"Backup falhou ({erro}). Nada foi gravado.")
    print(f"Backup feito: {arquivo}")


def confirmar(pergunta, sim):
    if sim:
        return True
    if not sys.stdin or not sys.stdin.isatty():
        print("Sem terminal para perguntar: use --sim se tiver certeza.")
        return False
    try:
        return input(f"{pergunta} Digite SIM para continuar: ").strip().upper() == "SIM"
    except (EOFError, KeyboardInterrupt):               # sem ninguém para responder (ou Ctrl+C): é um "não"
        print("Sem resposta.")
        return False


# ------------------------------------------------------------------ relatório
def escrever_relatorio(linhas, caminho):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    rotulo = {"criar": "criada", "pular": "pulada", "recusar": "recusada"}
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Linha", "Nome", "CPF", "Resultado", "Avisos e detalhes"])
        for L in linhas:
            w.writerow([L.n, L.nome, fmt_cpf(L.cpf) if L.cpf else "", rotulo.get(L.resultado, L.resultado), "; ".join(x for x in [L.detalhe, *L.avisos] if x)])


def resumo(linhas, criar):
    criadas = [L for L in linhas if L.resultado == "criar"]
    puladas = [L for L in linhas if L.resultado == "pular"]
    recusadas = [L for L in linhas if L.resultado == "recusar"]
    print(f"Linhas lidas: {len(linhas)}")
    print(f"  entrariam: {len(criadas)} internações de {len(criar)} pessoas novas")
    print(f"  puladas (já estão no sistema): {len(puladas)}")
    print(f"  recusadas (com erro): {len(recusadas)}")
    print(f"  linhas com aviso (entram mesmo assim): {sum(1 for L in criadas if L.avisos)}")
    sem_data = sum(1 for L in criadas if not L.entrada and not L.saida)
    print(f"  entram sem nenhuma data: {sem_data}")
    for titulo, grupo in (("PULADAS", puladas), ("COM ERRO", recusadas)):
        if grupo:
            print(f"\n{titulo} (as primeiras 15; o resto está no relatório):")
            for L in grupo[:15]:
                print(f"  linha {L.n}: {L.nome} — {L.detalhe}")


# ------------------------------------------------------------------ desfazer um lote
def mexida(i):
    """Alguém usou o registro depois da importação? Então não se apaga sozinho."""
    motivos = []
    for rel, rotulo in (("parcelas", "parcelas"), ("relatorio_social", "acolhimento social"), ("ficha_saude", "ficha de saúde"), ("relatorio_alta", "relatório de alta"),
                        ("registros_enfermagem", "registros de enfermagem"), ("evolucoes_saude", "evoluções"), ("anexos", "documentos anexados"),
                        ("versoes_relatorios", "histórico de versões"), ("notificacoes", "notificações")):
        if getattr(i, rel):
            motivos.append(rotulo)
    if (i.atualizado_em - i.criado_em).total_seconds() > 60 or (i.pessoa.atualizado_em - i.pessoa.criado_em).total_seconds() > 60:
        motivos.append("foi editado depois de importado")
    return motivos


def desfazer(lote, executar, sim):
    with exclusao.vendo_tudo():
        itens = db.session.execute(db.select(Internacao).filter(Internacao.origem.like(f"% | lote {lote}")).order_by(Internacao.id)).scalars().all()
        if not itens:
            print(f"Não há registros do lote {lote}.")
            return 1
        livres, presos = [], []
        for i in itens:
            m = mexida(i)
            (presos if m else livres).append((i, m))
        print(f"Lote {lote}: {len(itens)} internações. Podem ser apagadas: {len(livres)}. Ficam (alguém usou): {len(presos)}.")
        for i, m in presos[:15]:
            print(f"  fica: {i.pessoa.nome} — {', '.join(m)}")
        if not executar:
            print("\nSó simulei. Para apagar de vez as que podem ser apagadas, repita com --gravar.")
            return 0
        if not livres or not confirmar(f"Vai apagar DE VEZ {len(livres)} internações (e as pessoas que ficarem sem nenhuma).", sim):
            print("Nada foi apagado.")
            return 0
        fazer_backup()
        for i, _ in livres:
            exclusao.apagar(i)
    auditoria.registrar("importacao.lote", "", None, None, f"desfez o lote {lote}: {len(livres)} internações apagadas, {len(presos)} mantidas", usuario="importação")
    print(f"Pronto: {len(livres)} internações apagadas; {len(presos)} mantidas.")
    return 0


# ------------------------------------------------------------------ principal
def main(argv=None):
    ap = argparse.ArgumentParser(description="Importa ex-residentes de pastas e planilhas antigas para o sistema.", add_help=True)
    ap.add_argument("lista", nargs="?", help="a lista de importação (.xlsx ou .csv)")
    ap.add_argument("--gravar", action="store_true", help="grava de verdade (sem isto só simula)")
    ap.add_argument("--desfazer", metavar="LOTE", help="desfaz um lote importado (com --gravar apaga; sem, só simula)")
    ap.add_argument("--relatorio", help="onde guardar o relatório (CSV)")
    ap.add_argument("--usuario", default="importação", help="nome na trilha de auditoria")
    ap.add_argument("--sem-backup", action="store_true", help="não faz o backup antes (só para testes)")
    ap.add_argument("--sim", action="store_true", help="não pergunta antes de gravar")
    ap.add_argument("--pular-erros", action="store_true", help="grava mesmo havendo linhas com erro (elas ficam de fora)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass

    with app.app_context():
        if args.desfazer:
            return desfazer(args.desfazer, args.gravar, args.sim)
        if not args.lista:
            ap.error("diga a lista de importação")
        import catalogo
        linhas = ler_lista(args.lista, catalogo.atual())
        por_cpf, por_nome = pessoas_do_sistema()
        criar = decidir(linhas, por_cpf, por_nome)
        lote = datetime.now().strftime("%Y%m%d-%H%M%S")
        relatorio = Path(args.relatorio) if args.relatorio else RAIZ / "logs" / f"importacao-{lote}{'' if args.gravar else '-simulacao'}.csv"
        escrever_relatorio(linhas, relatorio)
        resumo(linhas, criar)
        print(f"\nRelatório: {relatorio}")
        erros = [L for L in linhas if L.resultado == "recusar"]
        if not args.gravar:
            print("\nSó simulei: nada foi gravado. Para gravar, repita o comando com --gravar.")
            return 0
        if erros and not args.pular_erros:
            print("\nHá linhas com erro: corrija a lista (ou use --pular-erros). Nada foi gravado.")
            return 1
        if not criar:
            print("\nNão há ninguém para importar.")
            return 0
        if not confirmar(f"\nVai gravar {sum(len(g['linhas']) for g in criar)} internações de {len(criar)} pessoas (lote {lote}).", args.sim):
            print("Nada foi gravado.")
            return 1
        if not args.sem_backup:
            fazer_backup()
        n_pessoas, n_internacoes = gravar(criar, lote)
        conferidas = db.session.execute(db.select(db.func.count(Internacao.id)).filter(Internacao.origem.like(f"% | lote {lote}"))).scalar()
        if conferidas != n_internacoes:
            print(f"ATENÇÃO: gravei {n_internacoes} internações mas o banco mostra {conferidas}. Confira antes de seguir.")
            return 1
        auditoria.registrar("importacao.lote", "", None, None, f"lote {lote}: {n_pessoas} pessoas e {n_internacoes} internações da lista {Path(args.lista).name}", usuario=args.usuario)
        print(f"\nPronto: {n_pessoas} pessoas e {n_internacoes} internações importadas (lote {lote}).")
        print(f"Para desfazer este lote (só o que ninguém mexeu): python importar_historico.py --desfazer {lote} --gravar")
        return 0


if __name__ == "__main__":
    sys.exit(main())
