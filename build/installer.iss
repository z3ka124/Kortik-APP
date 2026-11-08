; c:\Kortik\Kortik-Listener-App\build\installer.iss
; Inno Setup 6 skripta — per-user instalacija (bez admina), shortcuts i uninstaller.
; Build:  iscc /DMyAppVersion=0.1.0 /DSourceDir=build\output\KortikListener build\installer.iss

#define MyAppName "Kortik Listener"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\build\output\KortikListener"
#endif

[Setup]
AppId={{8E3F0B2D-77C4-4B1F-9B0E-KORTIKLISTENER01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Kortik
AppPublisherURL=https://kortikbot.xyz
AppSupportURL=https://kortikbot.xyz/support
DefaultDirName={localappdata}\Kortik\Listener\app
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\output\installer
OutputBaseFilename=KortikListener-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\KortikListener.exe
CloseApplications=yes
RestartApplications=no

[Languages]
; Inno Setup ne isporucuje uvek SerbianCyrillic.isl — koristimo ga samo ako postoji.
#if FileExists(AddBackslash(CompilerPath) + "Languages\SerbianCyrillic.isl")
Name: "serbian"; MessagesFile: "compiler:Languages\SerbianCyrillic.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Pokreni Kortik Listener sa Windows-om"; GroupDescription: "Startup"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\KortikListener.exe"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\KortikListener.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "KortikListener"; ValueData: """{app}\KortikListener.exe"""; \
    Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\KortikListener.exe"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Podaci korisnika (settings, DPAPI tajne, modeli) se NE brisu automatski.
Type: filesandordirs; Name: "{localappdata}\Kortik\Listener\app"
