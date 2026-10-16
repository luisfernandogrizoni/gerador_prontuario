# Roteiro do Windows, da rede e da sala (fase 6)

O sistema só é tão seguro quanto o computador que o guarda e a rede em que ele está. Este roteiro é o que **só uma pessoa na casa pode fazer**
(o sistema não alcança o roteador nem a sala). O que dá para conferir sozinho está no script `implantacao\verificar-servidor.ps1`: rode
**a cada 3 meses** (a página inicial avisa) e ele diz item por item o que está em ordem, o que precisa corrigir e o que conferir à mão.

Cada item abaixo diz **por que importa** em uma linha e **como fazer**. Marque o que já está feito.

## 1. O computador (o servidor)

- [ ] **Disco criptografado.** Sem isso, quem levar o computador (ou só o disco) lê o banco inteiro, sem precisar de senha nenhuma.
  - Windows 11 Home: *Configurações > Privacidade e segurança > Criptografia do dispositivo* (aparece se o computador tem TPM). Ligue.
  - Windows 11 Pro: *BitLocker* (pesquise "BitLocker" no menu Iniciar).
  - **A chave de recuperação**: o Windows guarda uma cópia na conta Microsoft (aka.ms/myrecoverykey). **Imprima ou anote em papel e guarde fora do
    computador**, junto da frase do backup. Sem ela, se o Windows pedir a chave (troca de peça, atualização grande), os dados ficam
    inacessíveis.
- [ ] **Atualizações automáticas ligadas.** A maioria dos ataques usa falha que já tem correção. *Configurações > Windows Update*: ligue e
  em *Opções avançadas > Horário ativo* ponha o expediente (o computador reinicia de madrugada e o sistema volta sozinho).
- [ ] **Antivírus ligado e atualizado.** O Microsoft Defender (já vem com o Windows) basta. *Segurança do Windows > Proteção contra vírus e ameaças*.
- [ ] **Duas contas no Windows**: uma de **administrador**, com senha forte, usada só para instalar e atualizar; e uma **comum**, para o uso
  do dia a dia. Quem usa a conta de administrador o dia todo entrega o computador a qualquer vírus. *Configurações > Contas > Outros usuários*.
- [ ] **Senha em todas as contas** e **conta Convidado desligada**. (O `verificar-servidor.ps1` confere.)
- [ ] **Sem entrada automática**: o Windows deve pedir senha ao ligar. (O sistema não precisa de ninguém logado: ele sobe sozinho, como tarefa.)
  Execute `netplwiz` e marque "Os usuários devem digitar um nome e uma senha".
- [ ] **Bloqueio de tela**: ao sair da sala, **Win + L**. E em *Configurações > Contas > Opções de entrada*, exigir senha ao acordar.
- [ ] **Área de trabalho remota desligada** (*Configurações > Sistema > Área de Trabalho Remota*) e **compartilhamento de arquivos desligado**
  se o computador não compartilha pastas. O acesso de fora do escritório é só pelo Tailscale (parte 5 do LEIA-ME).
- [ ] **A sala se tranca** e o computador fica onde só a equipe passa. Disco criptografado protege o disco desligado; o computador ligado e
  destrancado, não.
- [ ] **Rodar `implantacao\verificar-servidor.ps1`** (como Administrador) e corrigir o que sair em vermelho.

## 2. A rede do escritório e o roteador

Entre no painel do roteador (o endereço costuma ser `192.168.0.1` ou `192.168.1.1`; o `ipconfig` mostra em "Gateway padrão"). Os nomes dos
itens mudam de marca para marca; procure por estes:

- [ ] **Troque a senha do painel do roteador** (a de fábrica vem escrita embaixo do aparelho e é igual à de milhares de outros). Anote em papel.
- [ ] **Wi-Fi com WPA2 ou WPA3** e senha forte (frase de várias palavras). Nunca "WEP" nem rede aberta.
- [ ] **Rede de visitantes separada**: visitante, celular de passagem e aparelho de morador usam a rede "Convidados", que **não enxerga** os
  computadores da equipe. Só os computadores do escritório ficam na rede principal.
- [ ] **UPnP desligado** e **nenhum encaminhamento de portas** (port forwarding). Se existir algum, apague: o sistema **nunca** é
  exposto na internet (o acesso de fora é pelo Tailscale, que não abre porta).
- [ ] **Administração remota do roteador desligada** ("acesso remoto", "gerenciamento pela internet", "TR-069" quando não é do provedor).
- [ ] **Atualize o firmware do roteador** (e repita a cada 6 meses; se o fabricante parou de atualizar o modelo, troque o aparelho).
- [ ] **Reserva de IP para o servidor** ("DHCP estático"), para o endereço não mudar (o `LEIA-ME.md`, parte 2, explica).
- [ ] No Windows, a rede do escritório como **Privada** (*Configurações > Rede e Internet > a rede > Tipo de perfil de rede*).

## 3. Impressão

- [ ] A impressora fica **onde só a equipe passa**.
- [ ] Documento com dado sensível (ficha, prontuário, relatório social) **não fica na bandeja**: quem imprime, recolhe na hora.
- [ ] Papel descartado com dado de acolhido: **picotar** (ou queimar), nunca o lixo comum.

## 4. O que NÃO foi automatizado: o sistema rodando com conta limitada

Hoje o sistema e as tarefas (backup, cópia para os pen-drives, auditoria) rodam como **SISTEMA**, a conta mais poderosa do Windows. A ideia do
plano era trocar por uma conta comum, só com acesso à pasta do sistema: se alguém explorar uma falha do sistema, não ganharia o computador
inteiro.

**Não fiz isso por script, de propósito.** A troca mexe em permissões de pasta, em direitos de "logon como tarefa" e nas tarefas agendadas;
um erro derruba o sistema ou o backup, e isso não dá para testar sem o seu computador. O risco que ela evitaria já está bastante coberto
por outras camadas: a pasta `instance` (banco, chaves) é fechada só para o SISTEMA, os administradores e quem instalou; o sistema só escuta em
`127.0.0.1` (modo `https`); o firewall só abre para a rede local; e o navegador roda com política de conteúdo e token CSRF.

Se a casa quiser mesmo assim, o caminho seguro é **fazer junto, com backup recém-feito e uma janela de manutenção** (fora do expediente):
criar a conta, dar permissão só às pastas `instance`, `logs` e à de backup, trocar o dono das três tarefas, conferir que o sistema sobe depois de
um reinício e que o backup e a cópia externa funcionam, e ter o caminho de volta para SISTEMA anotado. Me avise e eu monto o roteiro com você.

## 5. A rotina (a cada 3 meses, uns 30 minutos)

1. `implantacao\verificar-servidor.ps1` (como Administrador) e corrigir o que sair em vermelho.
2. **Cadastros > Revisão**: conferir quem tem login, em que nível e quando entrou pela última vez; desativar quem saiu; marcar como revisada.
3. **Teste de restauração do backup** (`implantacao\RESTAURAR.md`, parte "Treino"): 2 minutos, com a frase do papel.
4. A auditoria das bibliotecas roda sozinha todo mês (`implantacao\auditar-dependencias.ps1 -Agendar`, uma vez); a página inicial avisa se achar algo.
5. A cada **6 meses**: reler `docs\plano-de-seguranca.md` e marcar a revisão do plano na mesma tela.
