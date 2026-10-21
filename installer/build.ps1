param([string]$OutputDirectory = (Join-Path $PSScriptRoot '..\build\installer'), [string]$ToolsDirectory)
$ErrorActionPreference='Stop'
$outputPath=[IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /target:winexe /optimize+ /platform:anycpu /codepage:65001 "/out:$outputPath\MI4-Sky-Installer.exe" /r:System.dll /r:System.Core.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll /r:System.Web.Extensions.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll "$PSScriptRoot\Installer.cs"
if($LASTEXITCODE -ne 0){throw 'C# build failed'}
if($ToolsDirectory){
 New-Item -ItemType Directory -Force -Path "$outputPath\tools" | Out-Null
 foreach($name in @('fastboot.exe','AdbWinApi.dll','AdbWinUsbApi.dll','NOTICE.txt')){
  Copy-Item -LiteralPath (Join-Path $ToolsDirectory $name) -Destination "$outputPath\tools\$name"
 }
 Write-Output 'Tool authenticity is checked at runtime. Only the pinned platform-tools 33.0.3 build is accepted.'
}
Write-Output "BUILT $outputPath\MI4-Sky-Installer.exe"
