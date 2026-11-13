# Geçersiz kabul koşusu (2026-11-13 20:16)
Araç hatası: `tools/local_acceptance/guard.py` içindeki `__aexit__` sarmalayıcısı argümansız çağrıyı kabul etmiyordu. Uygulamanın tarayıcı kapanışında 74 test, teardown aşamasında `TypeError` verdi. Bu koşunun KALDI sonuçları ürün veya test hatası değildir; kabul sonucu olarak kullanılmaz. Araç düzeltildi ve koşu yeniden yapıldı.
