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
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
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
pasta `models` apenas os modelos necessários às opções selecionadas, na primeira
utilização. A barra inferior mostra o andamento do download quando o servidor
informa o tamanho total.

Os downloads podem ocupar centenas de megabytes. Mantenha a conexão ativa e não
apague a pasta `models` enquanto o aplicativo estiver usando os modelos. Se um
download for interrompido, abra o app novamente para tentar de novo. Sem
internet ou sem um modelo disponível, os filtros clássicos continuam
funcionando.

O processamento por IA em CPU pode ser lento. Uma GPU NVIDIA compatível com
CUDA pode acelerar os modelos, mas não é obrigatória para os filtros clássicos.

## Resolução de problemas

- **`No module named 'cv2'` ou outra dependência ausente:** confirme que criou
  `.venv` com Python 3.12 e instale novamente com
  `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
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

## Licenças dos modelos

Os pesos GFPGAN e Real-ESRGAN são baixados dos projetos originais. Consulte as
licenças e condições de uso desses projetos antes de redistribuir os modelos ou
usar os resultados comercialmente.
