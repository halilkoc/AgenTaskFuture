"""Yerel Ar-Ge için MongoDB altyapı aracı (sökülebilir).

Bağımlılık yönü: geliştirme başlatıcısı → bu araç → normal uygulama. Uygulama (src/agentask) bu paketi
import etmez.
Kaldırmak için: tools/local_mongo/, compose.local-mongo.yml, .vscode/tasks.json içindeki "local-mongo"
görevleri ve
.env'deki LOCAL_MONGO_* araç anahtarları (LOCAL_MONGO_AUTOSTART=false kalabilir) silinir; uygulama kodu
değişmez.
"""
