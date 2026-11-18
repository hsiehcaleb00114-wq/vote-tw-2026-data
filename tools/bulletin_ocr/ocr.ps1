param([string]$ListFile)
# Windows 內建 OCR（zh-Hant-TW）。ListFile 每行：png 路徑<TAB>輸出 json 路徑
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) {
  $task = $asTaskGeneric.MakeGenericMethod($t).Invoke($null, @($op))
  $task.Wait(-1) | Out-Null
  $task.Result
}
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('zh-Hant-TW'))
foreach ($line in [IO.File]::ReadAllLines($ListFile)) {
  if (-not $line) { continue }
  $png, $out = $line.Split("`t")
  $png = $png.Replace('/', '\')
  if (Test-Path $out) { continue }
  try {
  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($png)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
  $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
  $words = New-Object System.Collections.Generic.List[object]
  $li = 0
  foreach ($l in $res.Lines) {
    foreach ($w in $l.Words) {
      $r = $w.BoundingRect
      $words.Add(@([math]::Round($r.X), [math]::Round($r.Y), [math]::Round($r.Width), [math]::Round($r.Height), $li, $w.Text))
    }
    $li++
  }
  $stream.Dispose()
  $json = ConvertTo-Json -InputObject @{ w = $bmp.PixelWidth; h = $bmp.PixelHeight; words = $words.ToArray() } -Depth 4 -Compress
  [IO.File]::WriteAllText($out, $json, [Text.UTF8Encoding]::new($false))
  } catch {
    $json = ConvertTo-Json -InputObject @{ error = $_.Exception.Message; words = @() } -Compress
    [IO.File]::WriteAllText($out, $json, [Text.UTF8Encoding]::new($false))
  }
}
