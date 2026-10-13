"""
Manual de Orientação para Candidatos e Familiares: o texto que a família recebe na internação, escrito com o motor de
documentos (documentos.py), no timbre do sistema.

O texto é o do manual do escritório (PDF de junho de 2025), sem mudar o que ele diz. Só foram arrumados erros de
digitação que não deixam dúvida ("não ser responsabilizará" -> "não se responsabilizará", um ponto solto no começo de
um item) e a pontuação de um item da lista de exclusão; a ortografia antiga (idéias, freqüência, auto-ajuda) ficou como está.
Para mudar o manual, é só mudar TEXTO abaixo: cada linha é ("tipo", texto) e o tipo diz como ela sai no papel:

    h    título de seção (negrito)          sub   subtítulo (negrito, recuado)
    p    parágrafo                          li    item de lista com marcador
    pt   parágrafo que começa com um título em negrito ("TÉRMINO DO TRATAMENTO: ...")
    ft   item de lista que começa com um nome sublinhado ("Disciplina: - o vício ...")
    il   linha recuada embaixo de um item   fim   fecho, centralizado
"""

from documentos import N, Pagina, Paragrafo, S, Texto

TEXTO = [
    ("h", "APRESENTAÇÃO:"),
    ("p", "A Casa de Acolhida Restauração é uma Comunidade Terapêutica Católica localizada na zona rural de Assis, tendo finalidade "
          "principal, acolher indivíduos do sexo masculino, maiores de 18 anos, que tenham o desejo firme e verdadeiro de lutar contra "
          "a dependência química ou o álcool. E que para tanto, necessitam de meios necessários e ajuda, para que possam iniciar um "
          "processo de recuperação dos vícios da droga e do álcool."),
    ("p", "Para ser admitido nesta Comunidade Terapêutica e participar de seu programa de recuperação, é imprescindível que o candidato "
          "observe e acolha as seguintes recomendações:"),
    ("li", "Que seja real, verdadeiro e sincero o seu desejo de abandonar definitivamente as drogas e o álcool;"),
    ("li", "Que não sofra de nenhum comprometimento psíquico grave que dificulte ou mesmo impossibilite-o de participar das atividades "
           "inerentes ao programa;"),
    ("li", "Que não necessite de acompanhamento médico-hospitalar complexo e constante obrigando-o a ausentar-se da Casa de Acolhida e "
           "de suas atividades cotidianas."),
    ("p", "Todo o programa de tratamento desenvolvido na Casa de Acolhida Restauração está fundamentado em três princípios básicos:"),
    ("li", "Espiritualidade,"),
    ("li", "Disciplina e,"),
    ("li", "Trabalho."),
    ("ft", "Espiritualidade:|- porque sentimos a necessidade de propor ao recuperando modelos que reforcem o seu desejo de mudar de vida. "
           "Acreditamos ser a espiritualidade cristã um tesouro de esperanças que muitas vezes o mundo moderno despreza, substituindo um "
           "ideal cristão por idéias consumistas que só produzem incertezas e desencantos;"),
    ("ft", "Disciplina:|- o vício ativa comportamentos de indisciplina e rebeldia e é necessário que se readquira condições para um novo "
           "aprendizado do saber ouvir, saber obedecer e saber fazer;"),
    ("ft", "Trabalho:|- acreditamos que o trabalho juntamente com a espiritualidade ajuda a resgatar a dignidade do indivíduo, "
           "transformando-o em indivíduo útil que busca resgatar a sua dignidade perdida pelos caminhos da dependência."),
    ("p", "O funcionamento desta Comunidade Terapêutica atende ao disposto na Resolução RDC n° 101, de 30 de maio de 2001 – ANVISA."),

    ("h", "PROPOSTA DE TRATAMENTO:"),
    ("p", "O tratamento do dependente deve ser visto como um processo dinâmico e complexo, que não vise única e exclusivamente a mera "
          "interrupção do uso das substâncias, mas sim que produza um conjunto de mudanças na vida futura deste indivíduo. As mudanças "
          "devem ser:"),
    ("ft", "mudanças psicossociais:| que objetivem a melhoria de suas relações sociais e familiares, que facilite seu retorno aos estudos "
           "ou ao trabalho e que produza uma ruptura verdadeira com os padrões de comportamentos anti-sociais que possuía;"),
    ("ft", "mudanças psicológicas:| que objetive ao indivíduo as condições para que se envolva com equilíbrio e continuidade nas relações "
           "afetivas, percebidas como gratificantes, gerando mais autonomia e responsabilidades;"),
    ("ft", "mudanças na saúde física:| que objetive dotar o indivíduo de capacidades para atuar preventivamente na identificação dos "
           "sintomas ou da manifestação de determinadas patologias levando-o a procurar a ajuda de profissionais da saúde, prevenindo-se "
           "assim, de doenças que ameaçam a sua integridade física e mental."),

    ("h", "OBJETIVOS:"),
    ("p", "Proporcionar ao dependente químico um ambiente adequado, com infra-estrutura e pessoal especializado, que favoreça o resgate de "
          "sua auto-estima, incentivando-o e motivando-o para que abandone a dependência e retorne ao seio familiar, restaurado física, "
          "psíquica e espiritualmente."),
    ("p", "Proporcionar as condições necessárias para a reflexão pessoal, permitindo que se desenvolva mudança de hábitos e de "
          "comportamentos."),

    ("h", "DURAÇÃO DO TRATAMENTO:"),
    ("p", "9 (nove) Meses"),

    ("h", "PROCESSO DE TRATAMENTO:"),
    ("p", "O processo de tratamento constará de quatro fases:"),
    ("sub", "FASE DE ADAPTAÇÃO: duração de um mês."),
    ("p", "No primeiro mês na Casa de Acolhida, o interno ficará alojado em quarto separado dos demais, sendo avaliado e acompanhado "
          "diuturnamente por um tutor especialmente designado pela coordenação. O recém chegado realizará atividades normais do programa "
          "sempre em companhia de seu tutor. Esse cuidado específico faz parte de seu processo de adaptação. Neste período não lhe será "
          "permitido o contato externo, quer seja por telefone, carta ou visita pessoal. Toda a informação que a família necessitar será "
          "prestada pelos responsáveis pela Casa;"),
    ("sub", "FASE DE TRATAMENTO INTENSIVO: duração de seis meses."),
    ("p", "Nesta fase o interno participa normalmente de todas as atividades previstas no programa de recuperação. Recebe "
          "acompanhamento espiritual e atendimento psicológico individual e em grupo."),
    ("sub", "FASE DE RESSOCIALIZAÇÃO duração de um mês."),
    ("p", "A ressocialização inicia após o quinto mês de tratamento."),
    ("sub", "FASE DE ACOMPANHAMENTO EXTERNO: duração de três meses."),
    ("p", "Após o processo de reinserção familiar e social, o interno deixa a Casa de Acolhida e retorna quando possível para sua família, "
          "sendo acompanhado à distância pela Casa de Acolhida. Neste período ele deverá participar ativamente dos grupos de auto-ajuda "
          "existentes em sua cidade, devendo manter-se permanentemente em contato com a coordenação do programa, situação em que "
          "informará sobre sua rotina de vida. Durante e mesmo após esse período, o recuperando poderá ser convidado a conversar com os "
          "internos da Casa, ocasião em que testemunhará sua luta e seu processo de recuperação. E se necessário poderá receber neste "
          "período o acompanhamento psicológico"),
    ("pt", "TÉRMINO DO TRATAMENTO:| Ao final dos nove meses o interno finalizará seu programa de recuperação. Nesta ocasião receberá "
           "orientações e incentivos para que continue participando das reuniões semanais dos grupos de auto-ajuda existentes em sua cidade."),

    ("h", "ESTRATÉGIAS DE TRATAMENTO:"),
    ("p", "As estratégias do programa oferecido pela Casa de Acolhida Restauração visam:"),
    ("li", "Integrar os internos no cotidiano da comunidade terapêutica;"),
    ("li", "Estimular o auto-conhecimento;"),
    ("li", "Ajudar a compreender o real significado do trabalho e da disciplina na sua vida;"),
    ("li", "Levar ao resgate de valores, princípios sociais e éticos;"),
    ("li", "Promover a vivência da espiritualidade numa perspectiva ecumênica;"),
    ("li", "Proporcionar o retorno ao convívio social e familiar;"),
    ("li", "Motivar à participação em grupos de apoio e auto-ajuda, como a Pastoral da Sobriedade, Amor Exigente, N.A e outros "
           "legalmente estabelecidos."),

    ("h", "EQUIPE TÉCNICA:"),
    ("p", "A equipe técnica que atua na Casa de Acolhida Restauração é composta de diretor geral, coordenador administrativo, psicólogos, "
          "assistente social e monitores. Alguns profissionais poderão atuar voluntariamente no programa, desde que previsto no plano de "
          "atividades da Casa."),

    ("h", "ATIVIDADES OBRIGATÓRIAS (DIÁRIO-SEMANAIS)"),
    ("li", "Atividades de espiritualidade:"),
    ("il", "Oração, reflexão, estudos bíblicos e etc."),
    ("li", "Atividades de apoio:"),
    ("il", "Atividades físicas:"),
    ("il", "Prática de esportes;"),
    ("il", "Atividades culturais e recreativas:"),
    ("il", "Música, teatro, exibição de filmes, etc."),
    ("li", "Atendimento Psicoterápico:"),
    ("il", "Atendimento psicológico individualizado e em grupo;"),
    ("li", "Laborterapia:"),
    ("il", "Manutenção do sítio, cuidado com os animais, horta, limpeza, jardinagem, cozinha, lavanderia e outros."),

    ("h", "PROCESSO DE INTERNAÇÃO"),
    ("p", "O dia e o horário previsto para o início da internação será estabelecido pela coordenação após a triagem e seleção, sempre "
          "obedecendo à disponibilidade de vagas."),
    ("li", "O recuperando deverá estar acompanhado de familiar ou responsável legal."),
    ("li", "Ter em mãos todo o material necessário para a internação (material de estudo, enxoval, fotos, itens e objetos de higiene "
           "pessoal, Bíblia, terço e medicamentos com receita médica), solicitados por ocasião da triagem."),
    ("li", "Estar em abstinência de álcool ou drogas por pelo menos 24 (vinte e quatro) horas."),
    ("li", "No dia de ingresso na Casa de Acolhida, o recuperando será submetido a uma rigorosa revista em seus pertences evitando que o "
           "mesmo traga consigo qualquer tipo de substância entorpecente."),

    ("h", "DIREITOS DOS INTERNOS"),
    ("li", "Conhecer antecipadamente, quando da triagem e seleção, a orientação que rege a rotina da Casa de Acolhida, os objetivos do "
           "programa de tratamento, bem como as regras internas de funcionamento;"),
    ("li", "Receber tratamento digno, respeitoso e seguro, independentemente de raça, credo religioso ou político, nacionalidade, "
           "preferência sexual, antecedentes criminais ou situações financeiras;"),
    ("li", "Conviver ainda que temporariamente em um ambiente sadio, livre de drogas, sexo e violência;"),
    ("li", "Não receber nenhum tipo de castigo físico ou ofensa moral que denigra sua dignidade;"),
    ("li", "Comunicar-se por telefone ou carta com a família, quando devidamente autorizado pela coordenação;"),
    ("li", "Receber a visita de familiares e amigos, bem como sair para visitas familiares de acordo com os prazos e condições "
           "estabelecidas;"),
    ("li", "Receber atendimento psicológico de qualidade e orientação espiritual que valorize sua luta contra a dependência e fortaleça "
           "sua crença religiosa;"),
    ("li", "Ser encaminhado para recursos externos em caso de doenças complexas ou quando a comunidade não dispor de meios para "
           "atendê-lo adequadamente. Neste sentido, a coordenação se responsabiliza em informar a família mantendo-a informada sobre o "
           "estado de saúde do interno."),

    ("h", "DEVERES DO INTERNO:"),
    ("li", "Envolver-se plenamente com tratamento participando sempre que possível de todas atividades previstas no programa;"),
    ("li", "Ter uma postura séria, discreta e atenta para com relação às atividades cotidianas do tratamento;"),
    ("li", "Ler, conhecer e respeitar de maneira integral o Regulamento e as Normas Internas de funcionamento da Casa de Acolhida;"),
    ("li", "Zelar pela guarda e manutenção de seus objetos pessoais;"),
    ("li", "Ser pontual com os horários estabelecidos para as atividades previstas no programa, bem como com a rotina da Casa de "
           "Acolhida;"),
    ("li", "Envolver-se integralmente na observância das atividades propostas pelo tratamento, a saber: atendimentos psicológicos, "
           "laborterapia, atividades de recreação e outras;"),
    ("li", "Participar intensamente das atividades de espiritualidade;"),
    ("li", "Conviver harmoniosamente com os demais internos, equipe técnica e coordenação;"),
    ("li", "Respeitar rigorosamente o cronograma de atividades e as normas de funcionamento da Casa;"),
    ("li", "Solicitar autorização da coordenação para o consumo de qualquer medicamento;"),
    ("li", "Solicitar autorização para saídas externas quando necessário e previsto no programa;"),
    ("li", "Acatar humildemente as correções que lhe forem impostas quando da inobservância do Regulamento ou das Normas Internas;"),
    ("li", "Não introduzir nas dependências da Casa, bem como portar ou fazer uso de qualquer tipo de substância química;"),
    ("li", "Comportar-se dignamente quando das saídas externas;"),
    ("li", "Comportar-se adequadamente dentro da Casa de Acolhida, evitando sempre que possível o uso de linguagens e expressões e/ou "
           "gírias características de grupos marginais."),

    ("h", "DESISTÊNCIA:"),
    ("p", "O recuperando poderá desistir do tratamento e da internação a qualquer momento, desde que comunique previamente à "
          "coordenação e seus familiares e/ou responsáveis. Estes deverão comparecer à Casa de Acolhida para a retirada de seus "
          "pertences."),
    ("p", "Em caso de desistência antes do término do tratamento, o recuperando só poderá retornar à Casa de Acolhida após um ano dessa "
          "desistência."),
    ("p", "O reingresso à Casa de Acolhida só poderá ocorrer por mais duas oportunidades, sempre obedecendo os prazos estabelecidos para "
          "a reinternação e a disponibilidade de vagas."),
    ("p", "Obs. Em caso de vaga social, a reinserção só ocorrerá após dois anos do abandono."),
    ("p", "Em caso de desistência do paciente, antes do término do primeiro mês, o valor pago no ato da internação, não será "
          "devolvido."),

    ("h", "DESLIGAMENTO TEMPORÁRIO:"),
    ("p", "Situações que requeiram internação hospitalar, repouso, controle de medicamentos e dieta alimentar, ou outras situações "
          "anormais, o recuperando poderá ser desligado temporariamente do programa, mantendo, porém, a vaga, que será ocupada assim "
          "que receber alta médica."),

    ("h", "A FAMÍLIA:"),
    ("p", "A família é co-responsável pelo processo de tratamento do recuperando e, para tanto deve ter consciência dos seus deveres e "
          "obrigações. Nenhum processo de recuperação é eficaz se não contar com a participação dos familiares. Para tanto, a família "
          "deverá observar e atender as seguintes solicitações:"),
    ("li", "Arcar sempre que possível com os custos de permanência do recuperando de acordo com o valor estabelecido pela "
           "coordenação;"),
    ("li", "Suprir o recuperando, sempre possível, de objetos de uso pessoal como enxovais, medicamentos, cigarros, etc, obedecendo o "
           "disposto nas normas de funcionamento da Casa;"),
    ("li", "Participar obrigatoriamente dos Grupos de Auto Ajuda (Pastoral da Sobriedade, Amor Exigente, N.A ou outros que funcionem "
           "dentro da lei);"),
    ("li", "Apresentar quando das visitas, declaração de freqüência ao Grupo de Auto Ajuda, emitida pelo responsável do Grupo;"),
    ("li", "Participar ativamente das últimas fases do tratamento (reinserção familiar e social e acompanhamento externo), criando "
           "condições para que o recuperando se familiarize com sua vida familiar e social."),

    ("h", "CRITÉRIOS DE SAÍDA:"),
    ("p", "Consultas médicas, odontológicas, internações de urgência, falecimento de familiares, perícias do INSS e/ou solicitações da "
          "Justiça."),
    ("p", "O recuperando será autorizado a deixar a Casa de Acolhida nas seguintes situações:"),
    ("li", "Atendimento de urgência em Pronto Socorro;"),
    ("li", "Consultas médicas e/ou odontológicas agendadas previamente e devidamente autorizadas pela coordenação;"),
    ("li", "Em caso de falecimento de familiares;"),
    ("li", "Para comparecer a perícias do INSS ou audiências junto ao Poder Judiciário;"),
    ("li", "Casos não contemplados neste item serão definidos e autorizados pela coordenação."),
    ("p", "OBS. Ao deixar a Casa de Acolhida para a fase de acompanhamento externo, cessará a contribuição financeira compulsória por "
          "parte da família do recuperando, ficando esta, livre para contribuir voluntária e livremente com o programa."),
    ("p", "Obs. Em todas essas saídas, o interno deverá se fazer acompanhar de um monitor especialmente designado pela coordenação."),
    ("p", "Em casos que requeiram internação hospitalar, repouso, controle de medicamentos e dieta alimentar, ou outras situações "
          "anormais, o recuperando poderá ser desligado temporariamente do programa, mantendo, porém, a vaga, a ser ocupada assim que "
          "obtiver condições para frequentar o programa."),

    ("h", "DAS VISITAS:"),
    ("sub", "Aos Internos:"),
    ("p", "Os internos que completaram a fase de adaptação (um mês de internação) poderão ser autorizados a receber a visita de "
          "familiares e amigos previamente cadastrados. As visitas ocorrerão no primeiro domingo de cada mês. Esta data poderá ser "
          "alterada a critério da coordenação, que comunicará com antecedência essas mudanças aos internos e seus familiares."),
    ("sub", "À Família:"),
    ("p", "As visitas à família poderão e deverão ser realizadas da seguinte forma:"),
    ("p", "O contato para a visita à família será realizado por carta ou telefone, conforme estabelecido pela coordenação, sempre "
          "obedecendo as Normas internas."),
    ("p", "Os horários e os dias determinados para o retorno das saídas deverão ser rigorosamente cumpridos. O não cumprimento dos "
          "prazos e normas, implicará em medidas de punição e mesmo na exclusão do programa."),

    ("h", "PROCEDIMENTOS A SEREM OBSERVADOS NAS VISITAS DE FAMILIARES E PESSOAS CADASTRADAS NA TRIAGEM."),
    ("li", "Ingresso nas dependências da Casa de Acolhida somente com autorização da coordenação;"),
    ("li", "Portar crachá de identificação;"),
    ("li", "Obedecer os horários de início (das 8h às 9h) e término (às 14h), conforme disposto nas normas internas da Casa;"),
    ("li", "Limite de no máximo de 05 (cinco) pessoas entre familiares e amigos cadastradas;"),
    ("li", "Crianças só acompanhadas de adultos responsáveis;"),
    ("li", "É obrigatório a apresentação de Declaração atualizada de freqüência regular a grupos de Auto-ajuda (Pastoral da Sobriedade, "
           "Amor Exigente, N.A ou outros legalmente reconhecidos.);"),
    ("li", "Todo material destinado ao interno (objetos de uso pessoal, alimentos, pertences, correspondências e outros), deverão ser "
           "identificados e entregues à coordenação. É proibido qualquer entrega de objetos ou materiais diretamente aos recuperandos."),
    ("li", "As famílias são as responsáveis pelos não familiares que trouxerem para a visita."),
    ("li", "As visitas deverão zelar pela ordem, limpeza e organização do espaço físico, instalações, móveis e equipamentos da Casa de "
           "Acolhida."),
    ("p", "Obs: Devemos ressaltar que formamos uma comunidade, com direitos e deveres iguais para todos os internos. Assim caso alguma "
          "família queira trazer algum tipo de agrado ou mimo, deverá se lembrar que existem outros internos na Casa e que tudo será "
          "partilhado, salvo objetos estritamente pessoais."),

    ("h", "COMUNICAÇÃO"),
    ("p", "Cartas: o recuperando poderá receber ou enviar correspondências, desde que respeite as normas internas da Casa. As "
          "correspondências recebidas serão abertas pela coordenação ou equipe de trabalho sempre na presença do recuperando;"),
    ("p", "Telefone fixo: Não é permitido o seu uso, salvo em caso de urgência, e desde que autorizado pela coordenação. Ligações "
          "interurbanas serão cobradas dos recuperandos."),
    ("p", "Celular: É terminantemente proibido seu uso. Os aparelhos ficarão sob guarda da coordenação."),

    ("h", "DESLIGAMENTO DO PROGRAMA"),
    ("sub", "Por iniciativa do recuperando (casos de desistência e/ou abandono)"),
    ("li", "A família será imediatamente comunicada e deverá comparecer para assinar o termo de desistência do tratamento e recolher os "
           "pertences do recuperando."),
    ("li", "Para desligar-se do programa o recuperando, independente do tempo de internação, deverá comunicar a equipe de internação "
           "com 24 (vinte e quatro) horas de antecedência."),
    ("p", "A instituição não se responsabilizará pelo transporte do recuperando, quando este, por qualquer motivo, optar pelo "
          "desligamento do programa. A instituição não se responsabilizará por fugas que possam ocorrer com o recuperando, pois os mesmos "
          "submetem-se ao tratamento por livre e espontânea vontade. Em caso de fugas, a coordenação considerará o ato como abandono e "
          "comunicará a família da ocorrência."),
    ("sub", "Por iniciativa da Instituição (casos de exclusão do programa)"),
    ("p", "O recuperando poderá ser excluído do programa quando:"),
    ("li", "Fizer uso de álcool, drogas ou medicamentos não autorizados e que se configurem como drogas;"),
    ("li", "Não cumprir as normas internas;"),
    ("li", "Recusar-se a participar das atividades do programa sem motivo justo."),
    ("li", "Ultrapassar sem autorização os limites territoriais da Casa de Acolhida;"),
    ("li", "Usar álcool ou drogas quando de suas saídas externas;"),
    ("li", "Influenciar de modo negativo ou provocar a discórdia entre os colegas internos;"),
    ("li", "Agredir fisicamente outro recuperando ou qualquer membro da equipe de trabalho ou da coordenação;"),
    ("li", "Apropriar-se intencionalmente e indevidamente de objetos ou pertences de terceiros ou da Instituição;"),
    ("li", "Praticar qualquer tipo de relação sexual ou promover atos de conotação sexual ou que incentivem e estimulem a "
           "sexualidade;"),
    ("li", "Incitar atos de rebeldia e indisciplina;"),
    ("li", "Guardar dinheiro escondido;"),
    ("li", "Insurgir-se indisciplinadamente e agressivamente contra o coordenador, membros da equipe técnica e outros internos;"),
    ("li", "Danificar propositadamente bens, equipamentos e/ou instalações da Casa de Acolhida;"),
    ("li", "Desrespeitar os voluntários, equipe técnica, coordenação e visitantes da Casa de Acolhida;"),
    ("li", "Por outros motivos que a equipe técnica e a coordenação julgarem como passíveis de exclusão."),

    ("h", "TÉRMINO DO TRATAMENTO:"),
    ("p", "Após ter cumprido o tempo de tratamento e não ter sido registrado qualquer tipo de recaída, o tratamento é dado por "
          "concluído, estando o recuperando apto a voltar para o convívio familiar e social."),

    ("h", "CONSIDERAÇÕES FINAIS"),
    ("p", "O êxito do tratamento é comemorado através de uma celebração eucarística, onde participam amigos, familiares e membros da "
          "Casa de Acolhida. Ao final dessa celebração, o recuperando recebe o certificado de conclusão do tratamento."),
    ("fim", "CASA DE ACOLHIDA RESTAURAÇÃO"),
]

TAMANHO = 11
RECUO, MARCADOR = 720, 360


def _bloco(tipo, texto):
    base = {"tamanho": TAMANHO}
    if tipo == "h":
        return Paragrafo([N(texto)], antes=14, depois=4, unido_ao_proximo=True, **base)
    if tipo == "sub":
        return Paragrafo([N(texto)], antes=8, depois=3, recuo=RECUO, unido_ao_proximo=True, **base)
    if tipo == "p":
        return Paragrafo([texto], "justificado", primeira_linha=RECUO, depois=5, **base)
    if tipo == "pt":
        titulo, resto = texto.split("|")
        return Paragrafo([N(titulo), resto], "justificado", primeira_linha=RECUO, antes=4, depois=5, **base)
    if tipo == "li":
        return Paragrafo([texto], "justificado", recuo=RECUO + MARCADOR, suspenso=MARCADOR, numero="•", depois=3, **base)
    if tipo == "ft":
        nome, resto = texto.split("|")
        return Paragrafo([S(nome), " " + resto.lstrip()], "justificado", recuo=RECUO + MARCADOR, suspenso=MARCADOR, numero="•", depois=3, **base)
    if tipo == "il":
        return Paragrafo([texto], "justificado", recuo=RECUO + MARCADOR, depois=3, **base)
    return Paragrafo([N(texto)], "centro", antes=26, **base)                 # fim


def blocos():
    """O manual: capa e, em página nova, o texto."""
    capa = [Pagina(),
            Paragrafo([Texto("MANUAL DE ORIENTAÇÃO", negrito=True)], "centro", tamanho=24, fonte="Times New Roman", antes=190),
            Paragrafo([Texto("PARA CANDIDATOS E FAMILIARES", negrito=True)], "centro", tamanho=24, fonte="Times New Roman", antes=14)]
    corpo = [_bloco(tipo, texto) for tipo, texto in TEXTO]
    corpo[0].quebra_antes = True
    return capa + corpo
