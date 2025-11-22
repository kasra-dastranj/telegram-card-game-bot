# 🚀 راهنمای Scale کردن به 10,000 کاربر همزمان

## 📊 محاسبات و نیازمندی‌ها:

### سناریو: 10,000 کاربر همزمان

**فرضیات:**
- هر کاربر: 2-3 request در دقیقه
- کل requests: ~20,000-30,000 req/min = **500 req/sec**
- هر request: ~50-200ms processing time
- Database queries: ~1,000-2,000 query/sec

---

## 🖥️ معماری پیشنهادی:

### **آرشیتکچر Multi-Server:**

```
                    ┌─────────────────┐
                    │  Load Balancer  │
                    │   (Nginx/HAProxy)│
                    └────────┬─────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
    ┌───────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
    │  Bot Server  │ │ Bot Server  │ │ Bot Server  │
    │   Instance 1 │ │ Instance 2  │ │ Instance 3  │
    │  (4GB/2CPU)  │ │ (4GB/2CPU)  │ │ (4GB/2CPU)  │
    └───────┬──────┘ └──────┬──────┘ └──────┬──────┘
            │                │                │
            └────────────────┼────────────────┘
                             │
                    ┌────────▼─────────┐
                    │  Redis Cluster   │
                    │  (Cache Layer)   │
                    │   (8GB RAM)      │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   PostgreSQL     │
                    │  (Primary DB)    │
                    │  (16GB/4CPU)     │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │   PostgreSQL     │
                    │  (Read Replica)  │
                    │  (8GB/2CPU)      │
                    └──────────────────┘
```

---

## 💰 هزینه‌ها و مشخصات سرورها:

### **گزینه 1: DigitalOcean / Linode**

#### 1. **Load Balancer:**
- **مشخصات:** Managed Load Balancer
- **هزینه:** $12/ماه
- **توضیح:** توزیع ترافیک بین bot instances

#### 2. **Bot Servers (3x):**
- **مشخصات:** 4GB RAM, 2 vCPU, 80GB SSD
- **هزینه:** $24/ماه × 3 = **$72/ماه**
- **توضیح:** هر instance می‌تونه 3,000-4,000 کاربر همزمان handle کنه

#### 3. **Redis Cache:**
- **مشخصات:** 8GB RAM, 2 vCPU
- **هزینه:** $48/ماه
- **توضیح:** Cache برای کاهش database load

#### 4. **PostgreSQL Primary:**
- **مشخصات:** 16GB RAM, 4 vCPU, 200GB SSD
- **هزینه:** $96/ماه
- **توضیح:** Database اصلی با write capability

#### 5. **PostgreSQL Read Replica:**
- **مشخصات:** 8GB RAM, 2 vCPU, 100GB SSD
- **هزینه:** $48/ماه
- **توضیح:** برای read queries (leaderboard, stats)

#### 6. **Monitoring (Optional):**
- **مشخصات:** Grafana + Prometheus
- **هزینه:** $12/ماه
- **توضیح:** مانیتورینگ و alerting

**💵 جمع کل: ~$288/ماه**

---

### **گزینه 2: AWS (مقیاس‌پذیرتر)**

#### 1. **Application Load Balancer:**
- **هزینه:** ~$20/ماه

#### 2. **EC2 Instances (3x t3.medium):**
- **مشخصات:** 4GB RAM, 2 vCPU
- **هزینه:** $30/ماه × 3 = **$90/ماه**

#### 3. **ElastiCache Redis:**
- **مشخصات:** cache.m5.large (6.38GB)
- **هزینه:** ~$80/ماه

#### 4. **RDS PostgreSQL (Multi-AZ):**
- **مشخصات:** db.m5.xlarge (16GB, 4 vCPU)
- **هزینه:** ~$280/ماه

#### 5. **RDS Read Replica:**
- **مشخصات:** db.m5.large (8GB, 2 vCPU)
- **هزینه:** ~$140/ماه

#### 6. **CloudWatch Monitoring:**
- **هزینه:** ~$10/ماه

**💵 جمع کل: ~$620/ماه**

---

### **گزینه 3: Hetzner (ارزان‌ترین)**

#### 1. **Load Balancer:**
- **مشخصات:** Nginx on CPX11 (2GB/2CPU)
- **هزینه:** €4.5/ماه (~$5/ماه)

#### 2. **Bot Servers (3x CPX21):**
- **مشخصات:** 4GB RAM, 3 vCPU, 80GB SSD
- **هزینه:** €8.9/ماه × 3 = **€26.7/ماه (~$30/ماه)**

#### 3. **Redis (CPX31):**
- **مشخصات:** 8GB RAM, 4 vCPU
- **هزینه:** €15.9/ماه (~$18/ماه)

#### 4. **PostgreSQL Primary (CPX41):**
- **مشخصات:** 16GB RAM, 8 vCPU, 240GB SSD
- **هزینه:** €29.9/ماه (~$33/ماه)

#### 5. **PostgreSQL Replica (CPX31):**
- **مشخصات:** 8GB RAM, 4 vCPU
- **هزینه:** €15.9/ماه (~$18/ماه)

**💵 جمع کل: ~$104/ماه** ⭐ **بهترین گزینه از نظر قیمت!**

---

## 🔧 تغییرات کد مورد نیاز:

### 1. **Migration به PostgreSQL:**

```python
# نصب dependencies
pip install psycopg2-binary sqlalchemy

# config.json
{
    "database": {
        "type": "postgresql",
        "host": "postgres-primary.example.com",
        "port": 5432,
        "database": "card_game",
        "user": "bot_user",
        "password": "secure_password",
        "read_replica": "postgres-replica.example.com"
    }
}

# game_core.py
import psycopg2
from psycopg2.pool import ThreadedConnectionPool

class DatabaseManager:
    def __init__(self, config):
        # Connection pool برای write
        self.write_pool = ThreadedConnectionPool(
            minconn=5,
            maxconn=20,
            host=config['host'],
            database=config['database'],
            user=config['user'],
            password=config['password']
        )
        
        # Connection pool برای read
        self.read_pool = ThreadedConnectionPool(
            minconn=10,
            maxconn=40,
            host=config['read_replica'],
            database=config['database'],
            user=config['user'],
            password=config['password']
        )
    
    def get_write_conn(self):
        return self.write_pool.getconn()
    
    def get_read_conn(self):
        return self.read_pool.getconn()
    
    def return_conn(self, conn, pool='write'):
        if pool == 'write':
            self.write_pool.putconn(conn)
        else:
            self.read_pool.putconn(conn)
```

### 2. **اضافه کردن Redis Cache:**

```python
# نصب redis
pip install redis

# cache_manager.py
import redis
import json
from typing import Optional, Any

class CacheManager:
    def __init__(self, redis_host='localhost', redis_port=6379):
        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=0,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
    
    def get(self, key: str) -> Optional[Any]:
        try:
            value = self.redis.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
        return None
    
    def set(self, key: str, value: Any, ttl: int = 300):
        try:
            self.redis.setex(
                key,
                ttl,
                json.dumps(value, default=str)
            )
        except Exception as e:
            logger.error(f"Redis set error: {e}")
    
    def delete(self, key: str):
        try:
            self.redis.delete(key)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
    
    def get_player_cards(self, user_id: int):
        key = f"player_cards:{user_id}"
        cached = self.get(key)
        if cached:
            return cached
        
        # دریافت از database
        cards = self.db.get_player_cards(user_id)
        
        # ذخیره در cache (5 دقیقه)
        self.set(key, [card.to_dict() for card in cards], ttl=300)
        return cards
    
    def invalidate_player_cards(self, user_id: int):
        self.delete(f"player_cards:{user_id}")
```

### 3. **Load Balancing با Webhook:**

```python
# telegram_bot.py
from telegram.ext import Application

# به جای polling از webhook استفاده کن
async def main():
    app = Application.builder().token(TOKEN).build()
    
    # تنظیم handlers
    setup_handlers(app)
    
    # استفاده از webhook
    await app.run_webhook(
        listen="0.0.0.0",
        port=8443,
        url_path=TOKEN,
        webhook_url=f"https://your-domain.com/{TOKEN}"
    )

if __name__ == '__main__':
    asyncio.run(main())
```

### 4. **Nginx Load Balancer Config:**

```nginx
# /etc/nginx/nginx.conf
upstream bot_backend {
    least_conn;  # توزیع بر اساس کمترین connection
    server 10.0.1.10:8443 max_fails=3 fail_timeout=30s;
    server 10.0.1.11:8443 max_fails=3 fail_timeout=30s;
    server 10.0.1.12:8443 max_fails=3 fail_timeout=30s;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /etc/ssl/certs/your-cert.pem;
    ssl_certificate_key /etc/ssl/private/your-key.pem;
    
    location / {
        proxy_pass http://bot_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

---

## 📈 مراحل Migration:

### **مرحله 1: تست محیط (هفته 1-2)**
1. راه‌اندازی PostgreSQL و Redis روی سرور تست
2. Migration کد و تست عملکرد
3. Load testing با 1,000 کاربر مجازی

### **مرحله 2: Setup Production (هفته 3)**
1. خرید و راه‌اندازی سرورها
2. نصب و پیکربندی PostgreSQL + Redis
3. Setup Load Balancer

### **مرحله 3: Migration تدریجی (هفته 4)**
1. Backup کامل از SQLite
2. Migration داده‌ها به PostgreSQL
3. تست با 10% ترافیک
4. افزایش تدریجی به 100%

### **مرحله 4: Monitoring (هفته 5+)**
1. نصب Grafana + Prometheus
2. تنظیم alerts
3. بهینه‌سازی بر اساس metrics

---

## 🎯 Performance Metrics مورد انتظار:

### با معماری پیشنهادی:

| Metric | مقدار |
|--------|-------|
| **کاربران همزمان** | 10,000-15,000 |
| **Requests/sec** | 500-800 |
| **Response Time** | 50-200ms |
| **Database Queries/sec** | 2,000-3,000 |
| **Cache Hit Rate** | 70-80% |
| **Uptime** | 99.9% |

---

## 💡 نکات مهم:

### ✅ **مزایا:**
- مقیاس‌پذیری بالا
- High Availability
- Performance عالی
- Monitoring حرفه‌ای

### ⚠️ **چالش‌ها:**
- پیچیدگی بیشتر
- نیاز به DevOps knowledge
- هزینه بالاتر
- نیاز به maintenance

### 🔧 **توصیه‌ها:**
1. شروع با Hetzner (ارزان‌ترین)
2. استفاده از Managed Services (کمتر دردسر)
3. Monitoring از روز اول
4. Backup روزانه خودکار
5. استفاده از CDN برای تصاویر

---

## 📞 زمان شروع Migration:

**شروع کنید وقتی:**
- ✅ بیش از 3,000 کاربر کل دارید
- ✅ بیش از 500 کاربر همزمان دارید
- ✅ Response time بیش از 1 ثانیه است
- ✅ Database size بیش از 2GB است

---

## 🚀 نتیجه:

برای **10,000 کاربر همزمان** نیاز داری:

### **گزینه پیشنهادی (Hetzner):**
- 💰 **هزینه:** ~$104/ماه
- 🖥️ **سرورها:** 5 سرور (LB + 3 Bot + Redis + PostgreSQL)
- ⚡ **Performance:** عالی
- 📈 **Scalability:** تا 15K کاربر همزمان

### **مراحل بعدی:**
1. بهینه‌سازی‌های فعلی رو انجام بده (انجام شد ✅)
2. وقتی به 3K کاربر رسیدی، شروع به برنامه‌ریزی migration کن
3. وقتی به 5K کاربر رسیدی، migration رو شروع کن
4. Scale up تدریجی تا 10K

**موفق باشی! 🎉**
