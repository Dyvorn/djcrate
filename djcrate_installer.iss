; DJ Crate Professional Windows Installer Script
; Inno Setup 6+ configuration with custom wizard graphics, modern UI, and file associations.

#define MyAppName "DJ Crate"
#define MyAppVersion "0.5.1"
#define MyAppPublisher "Dyvorn"
#define MyAppURL "https://github.com/Dyvorn/djcrate"
#define MyAppExeName "DJ Crate.exe"

[Setup]
AppId={{D1C7A7E0-3B4F-4B8A-9A2E-8E7D1A2B3C4D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=Releases
OutputBaseFilename=DJ_Crate_Installer
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
WizardSizePercent=110,110
WizardImageFile=assets\installer_sidebar.bmp
WizardSmallImageFile=assets\installer_header.bmp
DisableWelcomePage=no
ShowLanguageDialog=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
AppMutex=DJCrateAppMutex
CloseApplications=yes
CloseApplicationsFilter=*.exe,DJ Crate.exe
RestartApplications=no
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
UsePreviousPrivileges=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\DJ Crate\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// Helper function to find existing uninstall string from registry
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{D1C7A7E0-3B4F-4B8A-9A2E-8E7D1A2B3C4D}_is1';
  sUnInstallString := '';
  
  // Check HKCU (64-bit then 32-bit view)
  if not RegQueryStringValue(HKCU64, sUnInstPath, 'UninstallString', sUnInstallString) then
    if not RegQueryStringValue(HKCU32, sUnInstPath, 'UninstallString', sUnInstallString) then
      if not RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString) then
        // Check HKLM (64-bit then 32-bit view)
        if not RegQueryStringValue(HKLM64, sUnInstPath, 'UninstallString', sUnInstallString) then
          if not RegQueryStringValue(HKLM32, sUnInstPath, 'UninstallString', sUnInstallString) then
            RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString);
            
  Result := sUnInstallString;
end;

// Backup legacy portable data from old install dir to %APPDATA%\DJ Crate if present
procedure BackupLegacyAppData(OldAppDir: String);
var
  AppDataDir: String;
  LegacyDB: String;
  LegacySettings: String;
begin
  AppDataDir := ExpandConstant('{userappdata}\DJ Crate');
  ForceDirectories(AppDataDir);

  if (OldAppDir <> '') and DirExists(OldAppDir) then
  begin
    LegacyDB := AddBackslash(OldAppDir) + 'djcrate.db';
    if FileExists(LegacyDB) and not FileExists(AddBackslash(AppDataDir) + 'djcrate.db') then
    begin
      CopyFile(LegacyDB, AddBackslash(AppDataDir) + 'djcrate.db', False);
      Log('Migrated legacy djcrate.db from app dir to AppData.');
    end;

    LegacyDB := AddBackslash(OldAppDir) + 'database.db';
    if FileExists(LegacyDB) and not FileExists(AddBackslash(AppDataDir) + 'database.db') then
    begin
      CopyFile(LegacyDB, AddBackslash(AppDataDir) + 'database.db', False);
      Log('Migrated legacy database.db from app dir to AppData.');
    end;

    LegacySettings := AddBackslash(OldAppDir) + 'settings.json';
    if FileExists(LegacySettings) and not FileExists(AddBackslash(AppDataDir) + 'settings.json') then
    begin
      CopyFile(LegacySettings, AddBackslash(AppDataDir) + 'settings.json', False);
      Log('Migrated legacy settings.json from app dir to AppData.');
    end;
  end;
end;

// Terminate any running DJ Crate instance cleanly
procedure KillRunningApp();
var
  ResultCode: Integer;
begin
  // Attempt taskkill of running executable so files are not locked
  Exec('taskkill.exe', '/F /IM "DJ Crate.exe"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// Uninstall previous version before installing new files
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  sUnInstallString: String;
  sUninstaller: String;
  OldAppDir: String;
  ResultCode: Integer;
begin
  Result := '';
  sUnInstallString := GetUninstallString();
  
  if sUnInstallString <> '' then
  begin
    sUninstaller := RemoveQuotes(sUnInstallString);
    if FileExists(sUninstaller) then
    begin
      OldAppDir := ExtractFilePath(sUninstaller);
      
      // 1. Terminate running instances
      KillRunningApp();
      
      // 2. Safeguard legacy data
      BackupLegacyAppData(OldAppDir);
      
      // 3. Silently uninstall the old version
      // The silent uninstaller preserves AppData and user music
      if Exec(sUninstaller, '/VERYSILENT /NORESTART /SUPPRESSMSGBOXES', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      begin
        Log('Successfully uninstalled previous version (Exit code: ' + IntToStr(ResultCode) + ')');
        // Small delay to let Windows filesystem release directory handles
        Sleep(500);
      end
      else
      begin
        Log('Failed to execute previous uninstaller. Result code: ' + IntToStr(ResultCode));
      end;
    end;
  end;
end;

// Custom Uninstaller Step: protect user data
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataDir: String;
  PromptRes: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    AppDataDir := ExpandConstant('{userappdata}\DJ Crate');
    
    // If running silently (such as during an upgrade), ALWAYS preserve user data!
    if WizardSilent() then
    begin
      Log('Upgrade silent uninstall: Preserving user data in ' + AppDataDir);
      Exit;
    end;
    
    // If manual interactive uninstall by user from Windows Settings / Control Panel
    if DirExists(AppDataDir) then
    begin
      PromptRes := MsgBox(
        'Do you want to keep your DJ Crate library, crates, cue points, and settings?' #13#10 #13#10 +
        'Select "Yes" to keep your data for future installations (Recommended).' #13#10 +
        'Select "No" to completely remove your database and settings.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON1
      );
      
      if PromptRes = IDNO then
      begin
        Log('User chose to delete AppData: ' + AppDataDir);
        DelTree(AppDataDir, True, True, True);
      end
      else
      begin
        Log('User chose to preserve AppData: ' + AppDataDir);
      end;
    end;
  end;
end;
