<p align="center">
  <a href="../../README.md">🇬🇧 English</a> ·
  <a href="README.es.md">🇪🇸 Español</a> ·
  <a href="README.pt.md">🇵🇹 Português</a> ·
  <a href="README.fr.md">🇫🇷 Français</a> ·
  <a href="README.de.md">🇩🇪 Deutsch</a> ·
  <a href="README.it.md">🇮🇹 Italiano</a>
</p>

# KH PTZ Control: resumo em português

Controlo tátil de câmaras PTZ VISCA-over-IP num Raspberry Pi. O mapa numerado de lugares permite chamar enquadramentos guardados. O ecrã de utilizador tem um botão compacto para pôr as câmaras em standby e voltar a ligá-las, com confirmação (sem corte de energia), e Comments → Home guarda um enquadramento próprio ao manter o botão premido durante cinco segundos.

## Segurança: primeiro o STOP

- Ensaie CALL, SET, STOP e recuperação nas duas câmaras fora de uma reunião.
- O STOP tem prioridade na fila, mas a paragem física depende da câmara e da rede. Conheça a alternativa física caso a ligação se perca.
- O SET pode substituir posições na memória da câmara. Não repita uma gravação falhada nem apague dados para tentar reparar.
- Não abra um segundo controlador ou diagnóstico de rede ao mesmo tempo que a GUI em uso. Retire nomes, endereços e credenciais antes de partilhar registos.

## Requisitos e instalação

Alvo de instalação: Pi 4 ou 5, Raspberry Pi OS Bookworm de 64 bits com ambiente de trabalho, Python 3.11 do sistema, PyQt5 via `apt`, ecrã tátil e câmaras compatíveis numa rede acessível. Use uma sessão **X11**, não Wayland. Pi 4 com Bullseye/Python 3.9.2 é a base antiga; Trixie não está validado.

1. Escolha uma versão ou commit revisto e aprovado e faça uma cópia de segurança antes de alterar uma instalação existente.
2. No ambiente de trabalho, com o seu utilizador normal, clone o repositório e execute `bash install_khptz_rpi.sh --guide`.
3. Execute a verificação de preparação com o utilizador correto. Instale só se passar; se falhar, pare e siga a instrução indicada.
4. Siga a saída do instalador e o assistente inicial. Valide câmaras, enquadramentos e STOP fisicamente antes de usar em direto. Não use uma palavra-passe predefinida. No Bookworm não acrescente `--atem` nem `--dev` ao instalador.

Consulte o [guia de instalação (em espanhol)](../INSTALL_RPI_ES.md), o [guia de instalação em inglês](../INSTALL_RPI.md) e o [README em inglês](../../README.md) para ATEM, licenças e limites.
