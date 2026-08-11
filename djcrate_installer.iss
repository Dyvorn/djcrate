[Setup]
AppName=DJ Crate
AppVersion=1.0.0
AppPublisher=DJ Crate Contributors
AppPublisherURL=https://github.com/yourusername/dj-crate
DefaultDirName={pf}\DJ Crate
DefaultGroupName=DJ Crate
OutputDir=Releases
OutputBaseFilename=DJ_Crate_Installer
SetupIconFile=assets\icon.ico
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\DJ Crate\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\DJ Crate"; Filename: "{app}\DJ Crate.exe"; IconFilename: "{app}\assets\icon.ico"
Name: "{commondesktop}\DJ Crate"; Filename: "{app}\DJ Crate.exe"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon
Name: "{group}\{cm:UninstallProgram,DJ Crate}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\DJ Crate.exe"; Description: "{cm:LaunchProgram,DJ Crate}"; Flags: nowait postinstall skipifsilent

[Code]
// If we wanted to check for yt-dlp or ffmpeg we could do it here.
// For now, the app logic handles missing dependencies beautifully.
