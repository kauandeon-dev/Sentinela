; Instalador do Sentinela para Windows (Inno Setup 6).
;
; Instala a versão portátil completa (Python embutido, Sentinela, PostgreSQL e
; MariaDB portáteis) para o usuário atual, SEM administrador, em
; %LOCALAPPDATA%\Programs\Sentinela, com atalhos no Menu Iniciar e na Área de
; Trabalho. Gerado pelo portatil\montar.ps1:
;   ISCC /DPasta=<pasta montada> /DVersao=<versão> /DDestino=<saída> instalador.iss
;
; Atualizar por cima: o Sentinela em execução é encerrado antes de copiar os
; arquivos e, se o início automático estava ativo, volta em segundo plano.
; Desinstalar: encerra o Sentinela, remove o início automático e o banco de
; demonstração; as pastas dados\ e backups\ (configuração e cópias) ficam.

#ifndef Pasta
  #define Pasta "..\dist\Sentinela"
#endif
#ifndef Versao
  #define Versao "0.0.0"
#endif
#ifndef Destino
  #define Destino "..\dist"
#endif

[Setup]
AppId={{4F2A8C61-9B3E-4D7A-A5C2-8E61D0B7F3A9}
AppName=Sentinela
AppVersion={#Versao}
AppVerName=Sentinela {#Versao}
AppPublisher=Kauan V. Machado Deon
AppPublisherURL=https://github.com/kauandeon-dev/Sentinela
AppSupportURL=https://github.com/kauandeon-dev/Sentinela
AppComments=Backup automatizado de bancos de dados PostgreSQL e MariaDB/MySQL
DefaultDirName={autopf}\Sentinela
DefaultGroupName=Sentinela
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Destino}
OutputBaseFilename=Sentinela-Instalador
SetupIconFile=sentinela.ico
UninstallDisplayIcon={app}\Sentinela.exe
UninstallDisplayName=Sentinela
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
CloseApplications=no
SetupLogging=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho do Sentinela na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "{#Pasta}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "dados,backups,__pycache__"

[Icons]
Name: "{group}\Sentinela"; Filename: "{app}\Sentinela.exe"; WorkingDir: "{app}"; Comment: "Abre o painel do Sentinela"
Name: "{group}\Sentinela (demonstração)"; Filename: "{app}\Sentinela-Demo.exe"; WorkingDir: "{app}"; Comment: "Painel + banco PostgreSQL de exemplo"
Name: "{group}\Parar o Sentinela"; Filename: "{app}\Parar-Sentinela.exe"; WorkingDir: "{app}"; Comment: "Encerra o Sentinela que roda em segundo plano"
Name: "{group}\Trocar a senha do admin"; Filename: "{app}\Trocar-Senha.exe"; WorkingDir: "{app}"
Name: "{group}\Descriptografar cópias"; Filename: "{app}\Descriptografar.exe"; WorkingDir: "{app}"; Comment: "Gera o .sql da cópia mais recente de cada banco"
Name: "{group}\Pasta das cópias"; Filename: "{app}\backups"
Name: "{group}\Leia-me"; Filename: "{app}\LEIA-ME.txt"
Name: "{group}\Desinstalar o Sentinela"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Sentinela"; Filename: "{app}\Sentinela.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Dirs]
Name: "{app}\backups"

[Run]
; Atualização com o início automático ativo: volta a rodar em segundo plano
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\app\portatil.py"" --servico"; WorkingDir: "{app}"; Flags: nowait runhidden; Check: SegundoPlanoAtivo
Filename: "{app}\Sentinela.exe"; Description: "Abrir o Sentinela agora"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent
Filename: "{app}\Sentinela-Demo.exe"; Description: "Abrir com o banco de demonstração (para apresentar)"; WorkingDir: "{app}"; Flags: postinstall nowait skipifsilent unchecked

[UninstallRun]
Filename: "{app}\python\python.exe"; Parameters: """{app}\app\portatil.py"" --desinstalar"; WorkingDir: "{app}"; Flags: runhidden waituntilterminated; RunOnceId: "EncerrarSentinela"

[UninstallDelete]
; .pyc gerados pelo Python e o que mais for criado nas pastas do programa
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\ferramentas"
Type: dirifempty; Name: "{app}\backups"
Type: dirifempty; Name: "{app}"

[Code]
function SegundoPlanoAtivo: Boolean;
var
  Cmd: String;
begin
  Result := RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Sentinela', Cmd)
            and (Pos(Lowercase(ExpandConstant('{app}\app\portatil.py')), Lowercase(Cmd)) > 0);
end;

{ Atualização: encerra o Sentinela desta pasta (janela ou segundo plano) antes
  de substituir os arquivos. Um backup em andamento termina antes. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Py: String;
  Code: Integer;
begin
  Result := '';
  Py := ExpandConstant('{app}\python\python.exe');
  if FileExists(Py) then
    Exec(Py, '"' + ExpandConstant('{app}\app\portatil.py') + '" --parar', ExpandConstant('{app}'),
         SW_HIDE, ewWaitUntilTerminated, Code);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) and DirExists(ExpandConstant('{app}\dados')) then
    MsgBox('O Sentinela foi removido.' + #13#10#13#10 +
           'As configurações, a chave mestra e as cópias de backup foram mantidas em:' + #13#10 +
           ExpandConstant('{app}') + #13#10#13#10 +
           'Guarde a chave mestra (dados\sentinela.key) junto das cópias. Apague a pasta se não precisar mais delas.',
           mbInformation, MB_OK);
end;
