; --- DEFINIÇÕES GLOBAIS ---
; Este nome deve bater com o nome definido no .spec
#define MyAppName "FTP Utilities (Tailer & Sync)"
#define MyAppVersion "1.2"
#define MyAppPublisher "DSantos Info"
; *** ESTE NOME DEVE BATER COM O --name DO PYINSTALLER ***
; (O arquivo FTP_Utilities.spec usa este nome)
#define MyAppExeName "FTP_Utilities.exe"
#define MyAppFolderName "FTP Utilities"

[Setup]
; Gere um novo AppId único para cada aplicação
AppId={{8C798A3C-821A-483C-8A8D-2F38A88E5F98}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; {autopf} = C:\Program Files (x86). Use {autopf64} se o app for 64-bit.
DefaultDirName={autopf}\{#MyAppPublisher}\{#MyAppFolderName}
DisableProgramGroupPage=yes
; O nome do arquivo .exe final do instalador
OutputBaseFilename=setup_ftp_utilities_v{#MyAppVersion}

; *** CORREÇÃO IMPORTANTE ***
; O caminho agora é relativo. O script .iss deve ser executado
; a partir da pasta raiz do projeto (onde 'icon.ico' está).
SetupIconFile=icon.ico

Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; *** IMPORTANTE ***
; 1. O caminho da origem ("Source") é relativo.
; 2. Ele assume que você está executando o Inno Setup a partir da pasta
;    raiz do projeto (onde a pasta 'dist/' será criada pelo PyInstaller).
; 3. Copia APENAS o executável, pois usamos --onefile.
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Ícone no Menu Iniciar
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; Ícone na Área de Trabalho (se a tarefa "desktopicon" for marcada)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Executa a aplicação no final da instalação
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent