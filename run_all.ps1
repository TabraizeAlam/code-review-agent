$files = Get-ChildItem "sample_code\*.py"
$total = $files.Count
$i = 0

foreach ($file in $files) {
    $i++
    Write-Host ""
    Write-Host "[$i/$total] Reviewing: $($file.Name)" -ForegroundColor Cyan
    Write-Host ("-" * 60)

    "" | python main.py $file.FullName

    Write-Host ""
    Write-Host "Done: $($file.Name)" -ForegroundColor Green
}

Write-Host ""
Write-Host ("=" * 60) -ForegroundColor Yellow
Write-Host "All $total files reviewed. Reports saved as review_*.md" -ForegroundColor Yellow
