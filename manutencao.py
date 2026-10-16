"""
Manutenção contínua (plano de segurança, fase 9: docs/plano-de-seguranca.md). O que se esquece com o tempo, o sistema lembra:

  * **Auditoria mensal das dependências**: `implantacao/auditar-dependencias.ps1` roda o pip-audit (a lista pública de vulnerabilidades das
    bibliotecas Python) sobre as bibliotecas que o sistema usa de verdade e grava o resultado em `instance/auditoria_dependencias.json`; a
    tarefa agendada repete todo mês. Aqui o resultado vira aviso no quadro da página inicial (só para o administrador): vulnerabilidade
    conhecida, auditoria que falhou, ou auditoria que parou de rodar.
  * **Revisão trimestral dos acessos**: Cadastros > Revisão de acessos lista cada login com o funcionário, o nível, a última entrada e os
    pontos de atenção; o administrador marca como revisado e o aviso volta em 90 dias.
  * **Revisão semestral do plano de segurança**: o mesmo botão, a cada 180 dias.
  * **Verificação do servidor** (fase 6): `implantacao/verificar-servidor.ps1` grava `instance/verificacao_servidor.json`; aqui vira aviso se
    achou algo ou se passou de 100 dias sem rodar.
  * O **teste de restauração do backup** trimestral já é cobrado pela cópia externa (copia_externa.py).

Os avisos só aparecem no servidor do escritório (AVISAR_BACKUP=1), como os do backup, e só para o administrador.
Pelo terminal (usado pelo script):  python manutencao.py gravar-dependencias ARQUIVO.json   |   python manutencao.py falha-dependencias "texto"
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ARQUIVO_DEPENDENCIAS = "auditoria_dependencias.json"
ARQUIVO_VERIFICACAO = "verificacao_servidor.json"
ARQUIVO_REVISOES = "manutencao.json"

DIAS_DEPENDENCIAS = 45          # a auditoria é mensal; passou disso sem rodar, a tarefa parou
DIAS_ACESSOS = 90               # revisão dos acessos: trimestral
DIAS_PLANO = 180                # revisão do plano: semestral
DIAS_VERIFICACAO = 100          # verificação do servidor: trimestral
DIAS_SEM_ENTRAR = 90            # login que não entra há mais que isso é candidato a ser desativado
FERRAMENTAS = {"pip", "setuptools", "wheel", "pip-audit"}      # ferramentas de instalação: não atendem pedido nenhum, então a vulnerabilidade delas não vira aviso (o script atualiza o pip)


def _ler(instance, nome):
    try:
        dados = json.loads((Path(instance) / nome).read_text(encoding="utf-8-sig"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(instance, nome, dados):
    pasta = Path(instance)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    provisorio = arquivo.with_name(arquivo.name + ".tmp")
    provisorio.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(provisorio, arquivo)


def _quando(texto):
    try:
        return datetime.fromisoformat(texto) if texto else None
    except (TypeError, ValueError):
        return None


def _dias(agora, quando):
    return max((agora - quando).days, 0)


# ======================================================================== dependências
def gravar_dependencias(instance, bruto, agora=None):
    """Transforma o JSON do pip-audit (`--format json`) no resumo guardado. `bruto` = o texto ou o dicionário. Devolve o resumo."""
    agora = agora or datetime.now()
    dados = json.loads(bruto) if isinstance(bruto, (str, bytes)) else bruto
    pacotes = [p for p in dados.get("dependencies", []) if p.get("version")]
    vulneraveis = []
    for p in pacotes:
        achados = p.get("vulns") or []
        if achados and p["name"].lower().replace("_", "-") not in FERRAMENTAS:
            vulneraveis.append({"pacote": p["name"], "versao": p["version"],
                                "ids": [v.get("id", "?") for v in achados],
                                "corrigido_em": sorted({f for v in achados for f in (v.get("fix_versions") or [])})})
    resumo = {"em": agora.isoformat(timespec="seconds"), "pacotes": len(pacotes), "vulneraveis": vulneraveis, "erro": ""}
    _gravar(instance, ARQUIVO_DEPENDENCIAS, resumo)
    return resumo


def gravar_falha_dependencias(instance, texto, agora=None):
    """A auditoria não conseguiu rodar (sem internet, pip-audit fora do ar...): fica anotado, sem apagar o último resultado bom."""
    agora = agora or datetime.now()
    anterior = _ler(instance, ARQUIVO_DEPENDENCIAS)
    anterior.update({"erro": (texto or "erro desconhecido")[:300], "erro_em": agora.isoformat(timespec="seconds")})
    anterior.setdefault("vulneraveis", [])
    _gravar(instance, ARQUIVO_DEPENDENCIAS, anterior)


def resumo_dependencias(instance, agora=None):
    agora = agora or datetime.now()
    dados = _ler(instance, ARQUIVO_DEPENDENCIAS)
    em = _quando(dados.get("em"))
    return {"existe": bool(dados), "em": em, "dias": _dias(agora, em) if em else None, "pacotes": dados.get("pacotes", 0),
            "vulneraveis": dados.get("vulneraveis") or [], "erro": dados.get("erro") or "", "erro_em": _quando(dados.get("erro_em"))}


# ======================================================================== revisões feitas à mão
def marcar_revisao(instance, o_que, por, agora=None):
    """`o_que`: "acessos" ou "plano". Guarda quando e por quem."""
    assert o_que in ("acessos", "plano")
    dados = _ler(instance, ARQUIVO_REVISOES)
    dados[o_que] = {"em": (agora or datetime.now()).isoformat(timespec="seconds"), "por": por}
    _gravar(instance, ARQUIVO_REVISOES, dados)


def ultima_revisao(instance, o_que):
    """(quando, por) da última revisão, ou (None, '')."""
    item = _ler(instance, ARQUIVO_REVISOES).get(o_que) or {}
    return _quando(item.get("em")), item.get("por", "")


# ======================================================================== verificação do servidor (fase 6)
def resumo_verificacao(instance, agora=None):
    agora = agora or datetime.now()
    dados = _ler(instance, ARQUIVO_VERIFICACAO)
    em = _quando(dados.get("em"))
    itens = [i for i in (dados.get("itens") or []) if isinstance(i, dict)]
    return {"existe": bool(dados), "em": em, "dias": _dias(agora, em) if em else None,
            "atencao": [i for i in itens if i.get("situacao") == "ATENCAO"], "verificar": [i for i in itens if i.get("situacao") == "VERIFICAR"]}


# ======================================================================== os acessos (precisa do banco)
def situacao_dos_acessos(agora=None):
    """Um dicionário por login (usuários), com o funcionário, o nível, a última entrada e os pontos de atenção; e os totais."""
    from sqlalchemy import func

    import cadastros
    from modelos import Evento, Usuario, db
    agora = agora or datetime.now()
    ultimas = {nome: quando for nome, quando in db.session.execute(
        db.select(Evento.usuario, func.max(Evento.quando)).filter(Evento.acao == "login.ok").group_by(Evento.usuario))}
    por_login = {}
    for f in cadastros.funcionarios():
        if f.usuario:
            por_login.setdefault(f.usuario, f)
    administradores = {a.usuario for a in cadastros.administradores()}
    linhas = []
    for u in db.session.execute(db.select(Usuario).order_by(Usuario.nome)).scalars():
        f, ultima, pontos = por_login.get(u.nome), ultimas.get(u.nome), []
        dias_sem_entrar = _dias(agora, ultima) if ultima else None
        if f is None:
            pontos.append("Login sem funcionário: entra com o nível de menos acesso. Ligue a um funcionário ou desative o acesso.")
        elif not f.ativo:
            pontos.append("Funcionário desativado: o login não entra mais.")
        if f is not None and f.ativo:
            if ultima is None:
                pontos.append("Nunca entrou no sistema.")
            elif dias_sem_entrar > DIAS_SEM_ENTRAR:
                pontos.append(f"Não entra há {dias_sem_entrar} dias: ainda precisa de acesso?")
            if u.nome in administradores and not u.totp_ativo:
                pontos.append("Administrador sem o aplicativo autenticador.")
            if not f.email:
                pontos.append("Sem e-mail cadastrado.")
            elif not f.email_confirmado_em:
                pontos.append("E-mail ainda não confirmado.")
            if u.trocar_senha:
                pontos.append("Ainda não trocou a senha provisória.")
        linhas.append({"usuario": u.nome, "funcionario": f, "nivel": f.nivel.nome if f is not None and f.nivel else "", "ativo": bool(f is not None and f.ativo),
                       "ultima_entrada": ultima, "dias_sem_entrar": dias_sem_entrar, "administrador": u.nome in administradores,
                       "totp": u.totp_ativo, "pontos": pontos})
    sem_login = [f for f in cadastros.funcionarios() if f.ativo and not f.usuario]
    return {"linhas": linhas, "atencao": sum(1 for l in linhas if l["pontos"]), "ativos_sem_login": sem_login}


# ======================================================================== os avisos do quadro (só administrador, só no servidor)
def avisos(instance, agora=None):
    """Lista de (chave, texto, endpoint ou None, rótulo do botão ou None) do que está pendente."""
    if os.environ.get("AVISAR_BACKUP") != "1":
        return []
    agora = agora or datetime.now()
    lista = []

    dep = resumo_dependencias(instance, agora)
    if not dep["existe"]:
        lista.append(("manut:deps:nunca", "A auditoria das bibliotecas do sistema (vulnerabilidades conhecidas) ainda não foi feita. Rode "
                                          "implantacao\\auditar-dependencias.ps1 no servidor: ele faz a primeira e agenda a mensal.", None, None))
    else:
        if dep["vulneraveis"]:
            nomes = "; ".join(f"{v['pacote']} {v['versao']}" + (f" (corrigido na {', '.join(v['corrigido_em'])})" if v["corrigido_em"] else " (sem correção ainda)")
                              for v in dep["vulneraveis"][:5])
            mais = f" e mais {len(dep['vulneraveis']) - 5}" if len(dep["vulneraveis"]) > 5 else ""
            lista.append(("manut:deps:vulneravel", f"Bibliotecas com vulnerabilidade conhecida: {nomes}{mais}. Atualize o sistema (implantacao\\atualizar.ps1); "
                                                   "se o aviso continuar, a correção ainda não saiu: acompanhe.", None, None))
        if dep["erro"]:
            lista.append(("manut:deps:erro", f"A última auditoria das bibliotecas falhou ({dep['erro']}). Rode implantacao\\auditar-dependencias.ps1 de novo.", None, None))
        elif dep["dias"] is not None and dep["dias"] > DIAS_DEPENDENCIAS:
            lista.append(("manut:deps:velha", f"A auditoria das bibliotecas não roda há {dep['dias']} dias (a tarefa mensal parou?). "
                                              "Rode implantacao\\auditar-dependencias.ps1.", None, None))

    ver = resumo_verificacao(instance, agora)
    if not ver["existe"]:
        lista.append(("manut:servidor:nunca", "A verificação do servidor (disco criptografado, Windows, antivírus, rede) ainda não foi feita. Rode "
                                              "implantacao\\verificar-servidor.ps1 no servidor.", None, None))
    else:
        if ver["atencao"]:
            lista.append(("manut:servidor:atencao", "A verificação do servidor achou o que corrigir: " + "; ".join(i.get("item", "?") for i in ver["atencao"][:4])
                          + ". Rode implantacao\\verificar-servidor.ps1 para ver o que fazer.", None, None))
        if ver["dias"] is not None and ver["dias"] > DIAS_VERIFICACAO:
            lista.append(("manut:servidor:velha", f"A última verificação do servidor foi há {ver['dias']} dias. Rode implantacao\\verificar-servidor.ps1 (a cada 3 meses).", None, None))

    feita, _ = ultima_revisao(instance, "acessos")
    if feita is None or _dias(agora, feita) > DIAS_ACESSOS:
        quando = "nunca foi feita" if feita is None else f"foi há {_dias(agora, feita)} dias"
        lista.append(("manut:acessos", f"A revisão dos acessos (quem tem login, em que nível, quando entrou pela última vez) {quando}. Faça a cada 3 meses.",
                      "revisao_de_acessos", "Abrir a revisão"))
    feita, _ = ultima_revisao(instance, "plano")
    if feita is None or _dias(agora, feita) > DIAS_PLANO:
        quando = "nunca foi feita" if feita is None else f"foi há {_dias(agora, feita)} dias"
        lista.append(("manut:plano", f"A revisão do plano de segurança (docs\\plano-de-seguranca.md) {quando}. Faça a cada 6 meses e marque na revisão de acessos.",
                      "revisao_de_acessos", "Abrir a revisão"))
    return lista


# ======================================================================== terminal (usado por implantacao/auditar-dependencias.ps1)
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    instance = Path(__file__).resolve().parent / "instance"
    if len(argv) == 2 and argv[0] == "gravar-dependencias":
        try:
            resumo = gravar_dependencias(instance, Path(argv[1]).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError, KeyError) as erro:
            gravar_falha_dependencias(instance, f"não consegui ler o resultado do pip-audit ({type(erro).__name__})")
            print("Resultado ilegível.")
            return 1
        print(f"{resumo['pacotes']} bibliotecas conferidas; {len(resumo['vulneraveis'])} com vulnerabilidade conhecida.")
        for v in resumo["vulneraveis"]:
            print(f"  - {v['pacote']} {v['versao']}: {', '.join(v['ids'])} (corrigido em: {', '.join(v['corrigido_em']) or 'ainda não'})")
        return 0
    if len(argv) == 2 and argv[0] == "falha-dependencias":
        gravar_falha_dependencias(instance, argv[1])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
