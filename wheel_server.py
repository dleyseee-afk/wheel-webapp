import asyncio
import random
from datetime import datetime, timedelta
from aiohttp import web
import aiosqlite
from config import DATABASE_PATH

# Призы с весами (в процентах)
PRIZES = [
    {"name": "НИЧЕГО", "amount": 0, "weight": 75},
    {"name": "ПЕРЕКРУТ", "amount": 0, "weight": 5, "respin": True},
    {"name": "3₽", "amount": 3, "weight": 8},
    {"name": "5₽", "amount": 5, "weight": 7},
    {"name": "10₽", "amount": 10, "weight": 3},
    {"name": "15₽", "amount": 15, "weight": 1.5},
    {"name": "25₽", "amount": 25, "weight": 0.4},
    {"name": "50₽", "amount": 50, "weight": 0.1},
]

# Индексы призов на колесе (соответствуют HTML)
WHEEL_MAPPING = {
    "НИЧЕГО": [0, 2, 4, 6],
    "ПЕРЕКРУТ": [3],
    "3₽": [7],
    "5₽": [1],
    "10₽": [5],
    "15₽": [1],  # Показываем как 5₽ на колесе
    "25₽": [5],  # Показываем как 10₽ на колесе
    "50₽": [5],  # Показываем как 10₽ на колесе (редкий бонус)
}

COOLDOWN_HOURS = 48  # 2 дня


async def init_wheel_db():
    """Создать таблицу для колеса фортуны"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS wheel_spins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                prize TEXT,
                amount REAL,
                spun_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()


async def get_last_spin(user_id: int):
    """Получить время последнего спина"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            '''SELECT spun_at FROM wheel_spins 
               WHERE user_id = ? AND prize != 'ПЕРЕКРУТ'
               ORDER BY spun_at DESC LIMIT 1''',
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return datetime.fromisoformat(row[0])
        return None


async def can_spin(user_id: int) -> tuple[bool, str]:
    """Проверить, может ли пользователь крутить"""
    last_spin = await get_last_spin(user_id)
    
    if not last_spin:
        return True, ""
    
    next_spin = last_spin + timedelta(hours=COOLDOWN_HOURS)
    now = datetime.now()
    
    if now >= next_spin:
        return True, ""
    
    # Форматируем оставшееся время
    diff = next_spin - now
    hours = int(diff.total_seconds() // 3600)
    minutes = int((diff.total_seconds() % 3600) // 60)
    
    if hours > 0:
        time_str = f"{hours}ч {minutes}мин"
    else:
        time_str = f"{minutes}мин"
    
    return False, time_str


async def save_spin(user_id: int, prize: str, amount: float):
    """Сохранить результат спина"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            'INSERT INTO wheel_spins (user_id, prize, amount) VALUES (?, ?, ?)',
            (user_id, prize, amount)
        )
        await db.commit()


async def add_balance(user_id: int, amount: float):
    """Добавить баланс пользователю"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ?',
            (amount, user_id)
        )
        await db.commit()


def get_random_prize() -> dict:
    """Выбрать случайный приз с учётом весов"""
    total_weight = sum(p["weight"] for p in PRIZES)
    random_num = random.uniform(0, total_weight)
    
    current_weight = 0
    for prize in PRIZES:
        current_weight += prize["weight"]
        if random_num <= current_weight:
            return prize
    
    return PRIZES[0]  # НИЧЕГО по умолчанию


# === HTTP Handlers ===

async def handle_check(request):
    """Проверить кулдаун"""
    user_id = request.query.get('user_id')
    
    if not user_id:
        return web.json_response({"can_spin": True})
    
    try:
        user_id = int(user_id)
    except:
        return web.json_response({"can_spin": True})
    
    allowed, time_left = await can_spin(user_id)
    
    return web.json_response({
        "can_spin": allowed,
        "next_spin": time_left if not allowed else None
    })


async def handle_spin(request):
    """Крутить колесо"""
    try:
        data = await request.json()
        user_id = data.get('user_id')
        
        if not user_id:
            return web.json_response({"success": False, "message": "Ошибка авторизации"})
        
        user_id = int(user_id)
        
        # Проверяем кулдаун
        allowed, time_left = await can_spin(user_id)
        if not allowed:
            return web.json_response({
                "success": False, 
                "message": f"Подождите {time_left}",
                "next_spin": time_left
            })
        
        # Выбираем приз
        prize = get_random_prize()
        
        # Сохраняем спин
        await save_spin(user_id, prize["name"], prize["amount"])
        
        # Начисляем баланс если выигрыш
        if prize["amount"] > 0:
            await add_balance(user_id, prize["amount"])
        
        # Определяем индекс на колесе
        prize_indices = WHEEL_MAPPING.get(prize["name"], [0])
        prize_index = random.choice(prize_indices)
        
        return web.json_response({
            "success": True,
            "prize": {"name": prize["name"], "emoji": "🎁"},
            "prize_index": prize_index,
            "is_respin": prize.get("respin", False),
            "amount": prize["amount"]
        })
        
    except Exception as e:
        print(f"Spin error: {e}")
        return web.json_response({"success": False, "message": "Ошибка сервера"})


async def handle_static(request):
    """Отдать HTML страницу"""
    try:
        with open('webapp/wheel.html', 'r', encoding='utf-8') as f:
            content = f.read()
        return web.Response(text=content, content_type='text/html')
    except:
        return web.Response(text="File not found", status=404)


import os

async def start_wheel_server(host='0.0.0.0', port=None):
    port = port or int(os.environ.get('PORT', 8080))
    """Запустить веб-сервер для колеса"""
    await init_wheel_db()
    
    app = web.Application()
    app.router.add_get('/', handle_static)
    app.router.add_get('/wheel', handle_static)
    app.router.add_get('/api/wheel/check', handle_check)
    app.router.add_post('/api/wheel/spin', handle_spin)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    print(f"🎰 Wheel server started on http://{host}:{port}")
    return runner


if __name__ == "__main__":
    asyncio.run(start_wheel_server())
