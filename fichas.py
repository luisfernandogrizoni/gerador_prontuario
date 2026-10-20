"""
Documentos em branco que acompanham a triagem e a internação, escritos com o motor de documentos (documentos.py):

  * Pedido de exames        entregue à família quando a internação é marcada;
  * Enxoval                 a lista do que o acolhido leva, também entregue quando a internação é marcada;
  * Capa do envelope        a capa (em paisagem, sem timbre) do envelope do prontuário em papel;
  * Ficha multiprofissional ficha de saúde (anamnese), folha de enfermagem e folhas de evolução: a anamnese e a folha de enfermagem em branco, para
                            preencher à mão, ou com o que a enfermagem e a equipe escreveram no sistema (ficha_saude.py); as folhas de evolução só
                            saem com as anotações escritas no sistema, sem linhas em branco.

O texto vem dos modelos usados no escritório, com os erros de digitação corrigidos. Cada função devolve uma lista de
blocos que começa com um `Pagina(...)`, para poder ser colocada depois de qualquer outro documento (impressos.py).
O que o sistema já sabe do acolhido (nome, início, convênio, cidade) sai preenchido; o resto fica em branco.
"""

import ficha_saude
from servico_social import ENTRELINHA, ENTRELINHA_DO_TEXTO
from documentos import Celula, Coluna, Colunas, Formulario, Imagem, N, Pagina, Paragrafo, Pauta, Tabela, Texto, Titulo

SIM_NAO = "(    ) sim    (    ) não"
ALTURA_DA_LINHA = 19            # pontos entre uma linha de escrever e a próxima


def _nome(nome):
    """Linha pequena com o nome do acolhido, no alto de cada folha (uma folha solta não se perde de quem é)."""
    return Paragrafo([N("Acolhido(a): "), nome or "_" * 40], "direita", tamanho=9, depois=4)


# ======================================================================== pedido de exames
def pedido_de_exames(nome):
    exames = ["HIV;", "Sífilis;", "Hepatite B e C;", "Anti HBs e HBsAG;", "AntiHCV;", "VDRL;", "Hemograma Completo e Plaquetas."]
    return [Pagina(),
            Titulo("Pedido de exames", tamanho=14, antes=14, depois=16),
            Paragrafo([N("Acolhido(a): "), nome or "_" * 40], antes=0, depois=14),
            Paragrafo(["Encaminho a fazer os seguintes exames médicos para seu ingresso na Casa de Acolhida Restauração."],
                      "justificado", entrelinha=1.5),
            Paragrafo([N("TESTE RÁPIDO PARA:")], antes=22, depois=8),
            *[Paragrafo([N(exame)], recuo=720, suspenso=360, numero="•", entrelinha=1.5) for exame in exames]]


# ======================================================================== enxoval
ENXOVAL = [
    "02 lençóis de solteiro", "02 fronhas", "01 travesseiro", "02 cobertores", "02 toalhas de banho",
    "02 toalhas de rosto (opcional)", "03 calças jeans", "02 calças para trabalho", "05 camisetas para uso diário",
    "03 camisetas para trabalho", "01 jaqueta de frio", "01 blusa de frio", "02 bermudas", "02 shorts para futebol",
    "05 cuecas", "05 pares de meias", "01 par de botinas", "01 par de chinelos", "01 par de sapatos fechado",
    "01 par de tênis", "01 boné ou chapéu",
]
HIGIENE = [
    "06 aparelhos de barbear descartáveis", "01 creme de barbear", "01 escova de dente", "05 cremes dentais", "10 sabonetes",
    "02 desodorantes roll-on, aerosol ou pomada", "01 pente ou escova para cabelo", "02 shampoos", "01 condicionador",
    "01 creme hidratante", "01 cortador de unha", "01 bucha para banho", "01 repelente creme grande",
]
LIMPEZA = [
    "02 buchas para lavar roupa", "02 caixas de sabão em pó", "05 pedras de sabão", "01 litro de amaciante", "02 panos de chão",
    "01 vassoura", "01 rodo", "01 balde pequeno", "02 pacotes de prendedor de roupa",
]
ESTUDO = ["01 terço", "01 caderno", "02 canetas (azul/vermelha)", "02 lápis", "01 borracha", "01 Bíblia Ave Maria"]
ENTREGAR_NO_ESCRITORIO = ["Documentos pessoais (RG, CPF e Cartão SUS)", "Medicação com receita (caso esteja medicado)"]


def enxoval(nome=""):
    item = lambda texto: Paragrafo([texto], tamanho=11)
    secao = lambda titulo: Paragrafo([Texto(titulo, negrito=True, sublinhado=True)], tamanho=11, antes=12, depois=4, unido_ao_proximo=True)
    esquerda = [item(t) for t in ENXOVAL] + [secao("MATERIAL DE HIGIENE PESSOAL")] + [item(t) for t in HIGIENE]
    direita = ([secao("MATERIAL DE LIMPEZA")] + [item(t) for t in LIMPEZA]
               + [secao("MATERIAL DE ESTUDO")] + [item(t) for t in ESTUDO])
    direita[0].antes = 0
    return [Pagina(),
            Titulo("ENXOVAL", tamanho=14, antes=8, depois=10),
            Colunas([esquerda, direita], espaco=720),
            Tabela(colunas=[Coluna("ENTREGAR NO ESCRITÓRIO NO PRÉ DA INTERNAÇÃO", 6200)],
                   linhas=[[t] for t in ENTREGAR_NO_ESCRITORIO], tamanho=11, sombreado=False, cor_borda="000000", antes=16)]


# ======================================================================== capa do envelope
def capa_do_envelope(nome, inicio_fmt, convenio_sus, cidade):
    """Capa em paisagem, sem timbre, só com a logo. `convenio_sus`: True (Sim), False (Não) ou None (em branco).
    O motivo e o término ficam em branco: são marcados na baixa, à mão."""
    grande = lambda partes, **kw: Paragrafo(partes, **{"tamanho": 26, "fonte": "Arial", **kw})
    tamanho_do_nome = 26 if len(nome) <= 30 else 22 if len(nome) <= 38 else 18
    x = lambda marcado: "X" if marcado else " "
    return [Pagina(paisagem=True, timbre=False),
            Imagem("timbre/logo-topo.jpg", 28),
            grande([Texto(f"Nome: {nome}", negrito=True, sublinhado=True)], alinhamento="centro", tamanho=tamanho_do_nome, antes=6, depois=18),
            grande([N(f"Motivo: ( {x(False)} ) Conclusão     ( {x(False)} ) Desistência     ( {x(False)} ) Exclusão")], alinhamento="centro", antes=26, depois=36),
            grande([N(f"Início: {inicio_fmt}          Término:")], depois=12),
            grande([N(f"Convênio SUS: ( {x(convenio_sus is True)} ) Sim     ( {x(convenio_sus is False)} ) Não")], depois=12),
            grande([N(f"CIDADE: {cidade}")], fonte="Calibri")]


# ======================================================================== ficha multiprofissional de saúde
# Em branco (como o modelo do escritório) ou com o que a enfermagem e a equipe escreveram no sistema (ficha_saude.Conteudo): o desenho é o mesmo,
# com as respostas no lugar das linhas e as linhas em branco de sempre onde ainda não há resposta. A evolução é a exceção: não tem linhas em branco,
# a folha só existe com as anotações e cresce conforme os profissionais escrevem. O espaçamento é o do prontuário (veja servico_social.ENTRELINHA).
SISTEMAS = [nome for _, nome in ficha_saude.SISTEMAS]
SUBSTANCIAS = [nome for _, nome in ficha_saude.SUBSTANCIAS]
CATEGORIAS_DA_LINHA = (("medica", "MÉDICA"), ("enfermagem", "ENFERMAGEM"), ("nutricao", "NUTRIÇÃO"), ("psicologia", "PSICOLOGIA"),
                       ("assistencia_social", "ASSISTÊNCIA SOCIAL"))
LINHAS_MINIMAS_DA_TABELA = 6    # linhas da tabela de sinais vitais e linhas (de duas colunas) da evolução de enfermagem, no mínimo


def _marca(marcado):
    return f"( {'X' if marcado else ' '} )"


def _sim_nao(v, chave):
    """'( X ) sim    (    ) não' pela resposta; sem resposta, as duas caixas em branco, como no papel."""
    resposta = v.get(chave, "")
    if resposta not in ("sim", "nao"):
        return SIM_NAO
    return f"({' X  ' if resposta == 'sim' else '    '}) sim    ({' X  ' if resposta == 'nao' else '    '}) não"


def _resposta(texto):
    """O que foi digitado, em negrito e justificado (cada Enter é um parágrafo)."""
    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocos = [Paragrafo([N(linha or " ")], "justificado", antes=2 if k == 0 else 0, entrelinha=ENTRELINHA_DO_TEXTO) for k, linha in enumerate(linhas)]
    blocos[-1].depois = 8
    return blocos


def _pergunta(v, chave, texto, linhas=1, sim_nao=False, especifique="especifique"):
    """Pergunta + (sim/não, se `sim_nao`) + a resposta, ou linhas em branco para responder à mão."""
    blocos = [Paragrafo([texto], antes=18, depois=4, unido_ao_proximo=True)]
    resposta = v.get(chave + "_detalhe" if sim_nao else chave, "")
    if sim_nao:
        blocos.append(Paragrafo([f"{_sim_nao(v, chave)}.  Se sim, {especifique}:"], entrelinha=ENTRELINHA, unido_ao_proximo=True))
    if resposta:
        blocos += _resposta(resposta)
    elif not (sim_nao and v.get(chave) == "nao"):
        blocos.append(Pauta(linhas=linhas, altura=ALTURA_DA_LINHA, antes=4))
    return blocos


def _secao(titulo):
    return Paragrafo([Texto(titulo, negrito=True, italico=True)], "centro", antes=30, depois=10, unido_ao_proximo=True)


def _com_valor(rotulo, valor, vazio):
    """'Rótulo: valor' (o valor em negrito) ou, sem valor, 'Rótulo: ____'."""
    return [rotulo, N(valor)] if valor else [rotulo + vazio]


def _assinante(assinatura):
    """('Nome', 'cargo — COREN') de quem assinou, como ficou gravado ('Nome — cargo — COREN')."""
    partes = [p.strip() for p in (assinatura or "").split(" — ") if p.strip()]
    return (partes[0], " — ".join(partes[1:])) if partes else ("", "")


def _assinatura_curta(assinatura):
    """Para as colunas estreitas da tabela de enfermagem: 'Nome COREN-SP 123.456-ENF'."""
    partes = [p.strip() for p in (assinatura or "").split(" — ") if p.strip()]
    return " ".join([partes[0], partes[-1]]) if len(partes) > 2 else (partes[0] if partes else "")


def _depois_da_anamnese(c):
    """O fecho da anamnese: a linha de quem assina (com nome e COREN quando já foi finalizada no sistema)."""
    ficha = c.ficha if c else None
    if ficha is not None and ficha.finalizado and ficha.finalizado_em:
        nome, resto = _assinante(ficha.assinatura or ficha.finalizado_por)
        em = ficha.finalizado_em
        fecho = [Paragrafo([f"Finalizada no sistema em {em:%d/%m/%Y} às {em:%H:%M} por ", N(ficha.assinatura or ficha.finalizado_por)], antes=34),
                 Paragrafo(["_" * 42], "centro", antes=44, unido_ao_proximo=True),
                 Paragrafo([N(nome)], "centro", unido_ao_proximo=True), Paragrafo([resto], "centro", unido_ao_proximo=True)]
    else:
        fecho = ([Paragrafo(["Rascunho: ainda não finalizada no sistema."], antes=34)] if ficha is not None else []) \
            + [Paragrafo(["_" * 42], "centro", antes=44, unido_ao_proximo=True)]
    fecho += [Paragrafo(["Responsável pela Anamnese"], "centro", unido_ao_proximo=True), Paragrafo(["Carimbo e Assinatura"], "centro")]
    return fecho


def anamnese(nome, c=None):
    """Só a anamnese (a que se abre no histórico de versões), com o `Conteudo` dela."""
    return _anamnese(nome, c)


def _anamnese(nome, c=None):
    v = c.v if c else {}
    pagina1 = [Pagina(), _nome(nome),
               Paragrafo([N("FICHA MULTIPROFISSIONAL DE SAÚDE")], "centro", tamanho=13, antes=4, depois=4),
               Paragrafo([Texto("HISTÓRIA FISIOLÓGICA E PATOLÓGICA DO ACOLHIDO", negrito=True, italico=True)], "centro", antes=2, depois=16),
               Paragrafo(_com_valor("Altura (m): ", v.get("altura"), "_" * 18), antes=2, entrelinha=ENTRELINHA),
               Paragrafo(_com_valor("Peso (kg): ", v.get("peso"), "_" * 19), antes=2, entrelinha=ENTRELINHA),
               *_pergunta(v, "doencas_referidas", "Alguma vez algum médico ou um profissional de saúde lhe disse que você tinha algumas doenças?", 2),
               *_pergunta(v, "fratura", "Já sofreu alguma fratura?", sim_nao=True),
               *_pergunta(v, "cirurgia", "Já realizou alguma cirurgia?", sim_nao=True),
               *_pergunta(v, "alergia", "Possui alergia a algum alimento ou medicamento?", sim_nao=True),
               *_pergunta(v, "medicamentos", "Lista de medicamentos utilizados com posologia e horário:", 3),
               *_pergunta(v, "exames_previos", "Exames prévios realizados, data e resultados:", 3),
               *_pergunta(v, "tatuagem", "Tem tatuagem, cicatrizes ou piercing? Aponte a data da última realizada.", 2)]
    sistemas = [_secao("INVESTIGAÇÃO SOBRE DIVERSOS SISTEMAS")]
    for (chave, _), sistema in zip(ficha_saude.SISTEMAS, SISTEMAS):
        doenca, medicacao = v.get(f"sis_{chave}_doenca", ""), v.get(f"sis_{chave}_medicacao_detalhe", "")
        sistemas += [Paragrafo([N(f"Sistema {sistema}")], antes=16, unido_ao_proximo=True),
                     Paragrafo(_com_valor("Doença relacionada: ", doenca, "_" * 56), antes=2, entrelinha=ENTRELINHA, unido_ao_proximo=True),
                     Paragrafo(_com_valor(f"{_sim_nao(v, f'sis_{chave}_medicacao')}.  Se sim, faz uso de medicação: ", medicacao, "_" * 30), antes=2, entrelinha=ENTRELINHA)]
    pergunta_em_tratamento = lambda chave: Paragrafo([f"{_sim_nao(v, chave)}.  Se sim, especifique e em tratamento:"], antes=2, entrelinha=ENTRELINHA, unido_ao_proximo=True)

    def com_detalhe(chave):
        detalhe = v.get(chave + "_detalhe", "")
        return _resposta(detalhe) if detalhe else ([] if v.get(chave) == "nao" else [Pauta(linhas=1, altura=ALTURA_DA_LINHA, antes=4)])
    comorbidades = [Paragrafo([N("Outras comorbidades ou doença transmissível")], antes=22, unido_ao_proximo=True),
                    Paragrafo(_com_valor("Qual: ", v.get("comorbidade_qual"), "_" * 86), antes=2, entrelinha=ENTRELINHA, unido_ao_proximo=True),
                    Paragrafo([f"{_sim_nao(v, 'comorbidade')}.  Se sim, especifique e em tratamento:"], antes=2, entrelinha=ENTRELINHA, unido_ao_proximo=True),
                    *com_detalhe("comorbidade")]
    for chave, doenca in (("hiv", "HIV / AIDS"), ("tuberculose", "Tuberculose")):
        comorbidades += [Paragrafo([N(f"{doenca}:")], antes=16, unido_ao_proximo=True), pergunta_em_tratamento(chave), *com_detalhe(chave)]
    comorbidades += [Paragrafo([N("Doenças inflamatórias: "), f"{_sim_nao(v, 'inflamatorias')}.  Se sim, especifique e em tratamento:"], antes=18, entrelinha=ENTRELINHA, unido_ao_proximo=True),
                     *com_detalhe("inflamatorias"),
                     Paragrafo([N("Outras investigações:")], antes=18, depois=4, unido_ao_proximo=bool(not v.get("outras_investigacoes"))),
                     *(_resposta(v["outras_investigacoes"]) if v.get("outras_investigacoes") else []),
                     *_pergunta(v, "deficiencia", "Portador de deficiência física?", sim_nao=True)]
    dependencia = [_secao("INVESTIGAÇÃO SOBRE A DEPENDÊNCIA QUÍMICA"),
                   Paragrafo(["Quais substâncias de uso psicoativo:"], antes=10, depois=4, unido_ao_proximo=True)]
    for (chave, _), substancia in zip(ficha_saude.SUBSTANCIAS, SUBSTANCIAS):
        diario, periodo = v.get(f"sub_{chave}_diario", ""), v.get(f"sub_{chave}_periodo", "")
        dependencia += [Paragrafo([f"{_marca(bool(diario or periodo))} {substancia}  -  uso diário:  {_marca(diario == 'Sim')} sim   {_marca(diario == 'Não')} não"],
                                  antes=8, entrelinha=ENTRELINHA, unido_ao_proximo=True),
                        Paragrafo([f"      {_marca(periodo == ficha_saude.PERIODOS[0])} nos últimos 6 meses     {_marca(periodo == ficha_saude.PERIODOS[1])} no último mês"],
                                  entrelinha=ENTRELINHA)]
    dependencia += [Paragrafo([f"{_marca(bool(v.get('sub_outros')))} Outros: ", *([N(v["sub_outros"])] if v.get("sub_outros") else ["_" * 72])], antes=8, entrelinha=ENTRELINHA),
                    *_pergunta(v, "abstinencia", "Apresenta sintomas de abstinência?", 2),
                    *_pergunta(v, "cessar_sozinho", "Tentou cessar o uso por conta própria? Como foi?", 2),
                    *_pergunta(v, "inicio_uso", "Com qual idade o paciente começou a usar drogas e/ou álcool? Como se deu a descoberta do uso/vício e o padrão atual?", 3),
                    Paragrafo(["Possui histórico de tratamento anterior?"], antes=18, depois=4, unido_ao_proximo=True),
                    Paragrafo([f"{_sim_nao(v, 'tratamento_anterior')}.  Se sim, especifique:", *([" ", N(v["tratamento_anterior_detalhe"])] if v.get("tratamento_anterior_detalhe") else [])],
                              entrelinha=ENTRELINHA, unido_ao_proximo=True)]
    for (chave, _), tipo in zip(ficha_saude.TRATAMENTOS, ("Redução de danos / abstinência (Alcoólicos Anônimos e Narcóticos Anônimos, inclusive)",
                                                         "Internação em comunidade terapêutica", "CAPS / CAPS-AD")):
        dependencia += [Paragrafo([f"{_marca(v.get(chave) == 'sim')} {tipo}"], antes=12, entrelinha=ENTRELINHA, unido_ao_proximo=True),
                        Paragrafo(_com_valor("Obs: ", v.get(chave + "_detalhe"), "_" * 82), antes=2, entrelinha=ENTRELINHA)]
    dependencia += [Paragrafo([f"{_marca(v.get('trat_outros') == 'sim')} Outros / obs: ", *([N(v["trat_outros_detalhe"])] if v.get("trat_outros_detalhe") else ["_" * 66])], antes=12, entrelinha=ENTRELINHA),
                    *_pergunta(v, "clinicas_desejar", "O que estas clínicas de recuperação ou locais de tratamento deixaram a desejar do ponto de vista do familiar?", 3),
                    *_depois_da_anamnese(c)]
    return pagina1 + sistemas + comorbidades + dependencia


def _profissoes(marcadas):
    """A linha de categorias do alto da folha, '( X ) MÉDICA   (   ) ENFERMAGEM ...': com X as que já escreveram no sistema."""
    return "     ".join(f"({' X ' if chave in marcadas else '   '}) {nome}" for chave, nome in CATEGORIAS_DA_LINHA)


def _evolucao(nome, titulo="EVOLUÇÃO MULTIPROFISSIONAL", profissoes=True, data_carimbo="(Data/Carimbo/Assinatura)", entradas=()):
    """Uma folha de evolução: o título e as anotações escritas no sistema, uma depois da outra, com espaço entre elas. Não leva linhas em branco: a folha
    cresce conforme os profissionais escrevem e continua na página seguinte quando enche. Sem nenhuma anotação, a folha não sai. `entradas`: as
    evoluções modelos.EvolucaoSaude que saem nesta folha."""
    if not entradas:
        return []
    cabecalho = [Paragrafo([N(titulo)], "centro", tamanho=14, antes=2, depois=4)]
    if profissoes:
        cabecalho.append(Paragrafo([_profissoes({e.categoria for e in entradas})], "centro", tamanho=10, depois=2))
    cabecalho.append(Paragrafo([data_carimbo], "centro", tamanho=9, depois=10))
    escritas = []
    for e in entradas:
        categoria = ficha_saude.CATEGORIAS_DE_EVOLUCAO.get(e.categoria, (e.categoria,))[0]
        escritas += [Paragrafo([N(f"{e.criado_em:%d/%m/%Y} às {e.criado_em:%H:%M}"), f" — {categoria} — {e.criado_por}"], antes=16, depois=2, unido_ao_proximo=True),
                     *_resposta(e.texto)]
    return [Pagina(), _nome(nome), *cabecalho, *escritas]


def _enfermagem(nome, idade, registros=()):
    """Sistematização da assistência de enfermagem: folha em paisagem (a única da ficha). Ela precisa de toda a altura da
    folha, então não leva o timbre inteiro: só um cabeçalho pequeno, como no modelo. `registros`: modelos.RegistroEnfermagem, um por linha."""
    larguras = [1000, 800, 600, 700, 600, 600, 1500, 1000, 1200, 1500, 850, 1250, 1350, 1500]      # 14 colunas
    grupos = Formulario(grade=larguras, linhas=[[Celula("SINAIS VITAIS", 7, True), Celula("GLICEMIA CAPILAR", 3, True), Celula("PERDAS", 4, True)]],
                        alturas=[300], tamanho=9)
    titulos = ["HORÁRIO", "PA", "P", "TEMP", "FR", "BCF", "NOME LEGÍVEL", "HORÁRIO", "GLICEMIA CAPILAR", "NOME LEGÍVEL", "PESO",
               "VOLUME URINÁRIO (freq)", "EVACUAÇÃO (freq. e quant.)", "NOME LEGÍVEL"]
    em_branco = [":", "", "", "", "", "", "", ":", "", "", "", "", "", ""]
    linhas, evolucoes = [], []
    for r in registros:
        hora, nome_curto = f"{r.quando:%d/%m %H:%M}", _assinatura_curta(r.criado_por)
        vitais = any(x not in (None, "") for x in (r.pa, r.pulso, r.temperatura, r.fr, r.bcf))
        perdas = any(x not in (None, "") for x in (r.peso, r.volume_urinario, r.evacuacao))
        numero = lambda x, casas=1: "" if x is None else (f"{x:.{casas}f}".replace(".", ",") if isinstance(x, float) else str(x))
        linhas.append([hora if vitais else "", r.pa or "", numero(r.pulso), numero(r.temperatura), numero(r.fr), numero(r.bcf), nome_curto if vitais else "",
                       hora if r.glicemia else "", numero(r.glicemia), nome_curto if r.glicemia else "",
                       numero(r.peso), r.volume_urinario or "", r.evacuacao or "", nome_curto if perdas else ""])
        if r.evolucao:
            evolucoes.append(f"{r.quando:%d/%m/%Y %H:%M} — {r.evolucao} ({nome_curto})")
    linhas += [em_branco] * max(0, LINHAS_MINIMAS_DA_TABELA - len(linhas))
    celulas = evolucoes + [""] * (-len(evolucoes) % 2)
    pares = [celulas[k:k + 2] for k in range(0, len(celulas), 2)]
    pares += [["", ""]] * max(0, 8 - len(pares))
    return [Pagina(paisagem=True, timbre=False),
            Imagem("timbre/logo-topo.jpg", 15, "centro"),
            Paragrafo([N("Casa de Acolhida Restauração")], "centro", tamanho=14),
            Paragrafo([Texto("Por uma só vida já valeu a pena!", negrito=True)], "centro", tamanho=10),
            Paragrafo(["Rodovia Raposo Tavares, km 435 – Assis – SP"], "centro", tamanho=9, depois=6),
            Paragrafo([N("SISTEMATIZAÇÃO DA ASSISTÊNCIA DE ENFERMAGEM")], "centro", tamanho=12, depois=4),
            Formulario(grade=[9000, 5450], linhas=[[Celula(f"Nome: {nome}", 1), Celula("data:", 1)],
                                                   [Celula(f"Idade: {idade}", 2)]], alturas=[280, 280], tamanho=9),
            grupos,
            Tabela(colunas=[Coluna(t, l, "centro") for t, l in zip(titulos, larguras)], linhas=linhas, tamanho=8, altura_cabecalho=420,
                   sombreado=False, cor_borda="000000"),
            Tabela(colunas=[Coluna("EVOLUÇÃO DE ENFERMAGEM", 7225), Coluna("EVOLUÇÃO DE ENFERMAGEM", 7225)], linhas=pares, tamanho=9,
                   sombreado=False, cor_borda="000000"),
            Paragrafo(["Obrigatório Data/Carimbo/Assinatura"], "centro", tamanho=9, antes=3)]


def ficha_multiprofissional(nome, idade="", conteudo=None):
    """A ficha inteira: anamnese, evolução multiprofissional, folha de enfermagem e as anotações da coordenação e de outros profissionais. Sem `conteudo`
    sai em branco, para escrever à mão (sem as folhas de evolução, que só existem com anotações); com ele (ficha_saude.Conteudo), sai com o que foi
    escrito no sistema."""
    por_folha = {"multi": [], "coordenacao": [], "outros": []}
    for e in (conteudo.evolucoes if conteudo else ()):
        por_folha[ficha_saude.CATEGORIAS_DE_EVOLUCAO.get(e.categoria, ("", "outros"))[1]].append(e)
    return (_anamnese(nome, conteudo)
            + _evolucao(nome, entradas=por_folha["multi"])
            + _enfermagem(nome, idade, conteudo.registros if conteudo else ())
            + _evolucao(nome, "ANOTAÇÃO COORDENADOR OPERACIONAL", profissoes=False, data_carimbo="(Data/Carimbo e Assinatura)", entradas=por_folha["coordenacao"])
            + _evolucao(nome, "ANOTAÇÃO OUTROS PROFISSIONAIS", profissoes=False, data_carimbo="(Data/Carimbo e Assinatura)", entradas=por_folha["outros"]))
