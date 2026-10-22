# Lumina AI Studio

Aplicativo desktop para restaurar e ampliar fotos e vídeos. Inclui uma prévia
comparativa, filtros clássicos de imagem, restauração facial GFPGAN e upscaling
Real-ESRGAN.

## Requisitos

- Windows 10/11 de 64 bits.
- Python **3.12 de 64 bits**. Python 3.15 não é compatível com a versão de
  NumPy usada pelo projeto.
- Conexão com a internet na primeira utilização dos recursos de IA.
- Espaço livre em disco para as dependências, os modelos de IA e os arquivos
  processados.

O aplicativo também usa Tkinter, que normalmente acompanha o instalador oficial
do Python para Windows. Ao instalar Python, mantenha habilitada a opção **Tcl/Tk
and IDLE**.

## Instalação no Windows

Abra o PowerShell na pasta do projeto e execute os comandos abaixo:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

Se o comando `py` não estiver disponível, use o caminho completo do Python 3.12
instalado na máquina:

```powershell
& "C:\caminho\para\Python312\python.exe" -m venv .venv
```

Depois de criar o ambiente, instale os pacotes com os comandos acima e inicie o
aplicativo:

```powershell
.\.venv\Scripts\python.exe .\main.py
```

Não inicie o programa com outro Python do computador. Use sempre
`.venv\Scripts\python.exe` para garantir que as dependências instaladas para
este projeto sejam encontradas.

## Compilar e distribuir no Windows

Instale o [Inno Setup 6](https://jrsoftware.org/isinfo.php), depois instale as
dependências de compilação e gere a distribuição:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build_windows.ps1
```

Sem o Inno Setup, gere e valide somente a pasta portátil com
`.\build_windows.ps1 -PortableOnly`.

O build usa **PyInstaller `--onedir`** e Python 3.12 de 64 bits. A pasta
portátil completa fica em `dist\installer-build\LuminaStudio`; execute
`LuminaStudio.exe` dentro dela e mantenha a pasta `_internal` ao lado. **Não
copie nem distribua o executável sozinho**: o runtime inclui `python312.dll`,
as bibliotecas do Visual C++, Tcl/Tk e outros recursos dentro de `_internal`.
O erro `Failed to load Python DLL ...\internal\python312.dll` indica que o
executável foi separado de sua pasta de runtime ou que foi usado um pacote
antigo/incompleto.

O script valida a versão e arquitetura do interpretador e da DLL, o ambiente
virtual isolado, as versões do lock file e os arquivos essenciais da
distribuição antes de criar o instalador. O instalador
`dist\LuminaStudio-Setup.exe` instala a pasta completa, cria atalhos para o
executável com o ícone existente no pacote e pode ser removido pelas
configurações de aplicativos do Windows. A compilação mantém seus arquivos de
trabalho em `build\installer-build` e `dist\installer-build`.

Os modelos de IA baixados durante o uso ficam em
`%LOCALAPPDATA%\LuminaStudio\models`, uma pasta gravável pelo usuário e
independente da pasta de instalação.

As preferências ficam em `%APPDATA%\LuminaStudio\preferences.json`, fora da
pasta do executável e do diretório interno do PyInstaller. As traduções são
recursos empacotados em `locales` e são localizadas a partir do diretório interno
do aplicativo, nunca do diretório de trabalho atual.

`requirements-lock.txt` fixa as versões testadas para um ambiente limpo. Ao
atualizar dependências, instale e teste as novas versões e atualize o lock file
com `.\.venv\Scripts\python.exe -m pip freeze --local` antes de distribuir.

Execute a suíte de testes com:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Como usar

1. Clique em **Abrir foto ou vídeo** e escolha um arquivo. Também é possível
   arrastar um arquivo para a área da prévia, se o suporte a arrastar e soltar
   estiver disponível.
2. Ajuste as opções no painel. Passe o cursor sobre a barra de rolagem ou use a
   roda do mouse para ver todas as configurações.
3. Arraste a linha vertical sobre a prévia para comparar antes e depois. Use o
   botão direito do mouse para escolher outra área da imagem.
4. Clique em **Processar e salvar** e escolha onde guardar o resultado. A
   imagem editada é salva primeiro; quando a IA estiver disponível, o aplicativo
   pode substituí-la pela versão aprimorada.

Formatos de imagem aceitos: JPG/JPEG, PNG, BMP, WEBP e TIFF. Formatos de vídeo
aceitos: MP4, MOV, AVI, MKV, WEBM e M4V.

## Modelos de IA e downloads

Os pesos dos modelos não são incluídos no repositório. O aplicativo baixa para a
pasta `%LOCALAPPDATA%\LuminaStudio\models` apenas os modelos necessários às
opções selecionadas, na primeira utilização. A barra inferior mostra o
andamento do download quando o servidor informa o tamanho total.

Os downloads podem ocupar centenas de megabytes. Mantenha a conexão ativa e não
apague a pasta `models` enquanto o aplicativo estiver usando os modelos. Se um
download for interrompido, abra o app novamente para tentar de novo. Sem
internet ou sem um modelo disponível, os filtros clássicos continuam
funcionando.

O processamento por IA em CPU pode ser lento. Uma GPU NVIDIA compatível com
CUDA pode acelerar os modelos, mas não é obrigatória para os filtros clássicos.
Para reduzir o tempo de upscaling em computadores sem CUDA, a opção **Acelerar
IA em CPU** vem ativada. Ela calcula direto perto da resolução final quando o
fator de ampliação é menor que 4×; isso pode reduzir alguns detalhes. Desative-a
para manter o processamento original do modelo.

## Resolução de problemas

- **`No module named 'cv2'` ou outra dependência ausente:** confirme que criou
  `.venv` com Python 3.12 e instale novamente com
  `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- **O aplicativo não inicia após a instalação:** reinstale usando
  `dist\LuminaStudio-Setup.exe`. Não execute uma cópia isolada de
  `LuminaStudio.exe` da Área de Trabalho ou do OneDrive: use o atalho criado
  pelo instalador ou mantenha o executável junto à pasta `_internal` completa.
  Se o erro de DLL continuar mesmo com o pacote íntegro, instale ou repare o
  Microsoft Visual C++ Redistributable 2015–2022 x64 pelo site oficial da
  Microsoft. Para atualizar ícones antigos da barra de tarefas, desafixe o
  atalho antigo e fixe novamente o criado pelo instalador atualizado.
- **A janela fecha ou aparece um traceback:** inicie pelo PowerShell usando
  `.\.venv\Scripts\python.exe .\main.py` para que a mensagem de erro fique
  visível.
- **Os controles de vídeo não aparecem ativos:** estabilização e interpolação
  só são habilitadas depois de abrir um vídeo.
- **A IA não baixa:** confirme o acesso à internet e tente novamente. O app
  ainda pode processar com os ajustes clássicos.
- **Não é possível abrir a janela:** verifique se o Python foi instalado com
  Tcl/Tk.

## Estrutura

- `main.py`: interface gráfica.
- `engine.py`: filtros, leitura/escrita e processamento de imagens e vídeos.
- `ai.py`: download e carregamento dos modelos de IA.
- `requirements.txt`: dependências Python.
- `requirements-lock.txt`: versões fixas para builds reproduzíveis.
- `requirements-build.txt`, `build_windows.ps1`, `build_support.py` e
  `LuminaStudio.iss`: validação e configuração do build/instalador Windows.
- `app_support.py`: caminhos de recursos, preferências, temas e formatação.
- `locales\`: catálogos de interface pt-BR, English e Español.
- `tests\`: testes de interface, localização, empacotamento e processamento.
- `assets\lumina.ico`: ícone do aplicativo e do instalador.

## Aparência e idioma

Na seção **Preferências**, escolha o modo **Automático**, **Claro** ou
**Escuro** e o idioma **Português (Brasil)**, **English** ou **Español**. As
seleções são aplicadas sem recriar a janela nem perder os ajustes da sessão. O
modo automático acompanha a preferência de aplicativos do Windows; em outros
sistemas ou se essa configuração não estiver disponível, usa o tema claro.
O Tkinter não oferece desfoque/transparência de fundo portátil nem cantos
arredondados nativos acessíveis; o design usa superfícies foscas opacas,
contraste e foco visível em vez de simular efeitos incompatíveis.

## Licenças dos modelos

Os pesos GFPGAN e Real-ESRGAN são baixados dos projetos originais. Consulte as
licenças e condições de uso desses projetos antes de redistribuir os modelos ou
usar os resultados comercialmente.
