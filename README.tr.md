# ArtoDownloader

<p align="center"><img src="assets/icon.png" width="128" alt="ArtoDownloader"></p>

IDM mantığıyla çalışan, **çok parçalı**, **duraklatılıp devam ettirilebilen** indirme yöneticisi. LibreWolf / Firefox eklentisi tarayıcıdaki indirmeleri yakalar ve ArtoDownloader'a devreder.

## Özellikler
- 8 paralel bağlantı (HTTP `Range`), parçalar doğrudan dosyanın ilgili ofsetine yazılır (sonda birleştirme yok)
- Dinamik bölme: boşta kalan bağlantı, en çok işi kalan parçanın yarısını devralır
- Duraklat / Devam et. Durum `.arto` dosyasında tutulur, pencereyi kapatsanız bile devam edilebilir
- Hata durumunda otomatik yeniden deneme. Sunucu `Range` desteklemiyorsa tek akışla indirir
- Modern koyu arayüz: canlı hız, hız grafiği, parça haritası, kalan süre
- Büyük dosyalarda hızlı başlangıç (NTFS sparse dosya, ilk bağlantının yeniden kullanımı)
- Host hata verirse tarayıcının kendi indirmesine döner

## Kurulum
1. [Releases](../../releases) sayfasından `ArtoDownloader-Setup.exe` dosyasını indirip çalıştırın.
2. Kurulumun sonunda "Eklentiyi LibreWolf'a yükle" kutusunu işaretli bırakın ve onay verin.
   Elle yüklemek için `about:addons` → dişli → **Dosyadan eklenti yükle** → kurulum klasöründeki `artodownloader.xpi`.
3. İmza hatası alırsanız `about:config` içinde `xpinstall.signatures.required` değerini `false` yapın.

## Mimari
```
LibreWolf eklentisi ──native messaging──▶ ArtoHost.exe ──▶ ArtoDownloader.exe (arayüz + indirme motoru)
```
- `extension/` tarayıcı eklentisi (indirmeyi yakalar, çerez ve referer'ı iletir)
- `host/host.py` native messaging host
- `host/app.py` indirme motoru, `host/ui.py` arayüz

## Kaynaktan derleme
Gereksinimler: Python 3.10+, `pip install pyinstaller pillow`, [Inno Setup 6](https://jrsoftware.org/isinfo.php).
```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```
Çıktı: `dist\ArtoDownloader-Setup.exe`

## Lisans
MIT
