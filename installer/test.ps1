$ErrorActionPreference='Stop'
$out=Join-Path $PSScriptRoot '..\build\tests'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /target:exe /main:Mi4Sky.Tests /codepage:65001 "/out:$out\InstallerTests.exe" /r:System.dll /r:System.Core.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll /r:System.Web.Extensions.dll /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll "$PSScriptRoot\Installer.cs" "$PSScriptRoot\InstallerTests.cs"
if($LASTEXITCODE -ne 0){throw 'Test build failed'}
& "$out\InstallerTests.exe"
if($LASTEXITCODE -ne 0){throw 'Installer tests failed'}
