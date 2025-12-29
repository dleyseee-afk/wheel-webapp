import aiosqlite
from config import DATABASE_PATH

async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0,
                banned INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                service_id TEXT,
                service_name TEXT,
                quantity INTEGER,
                price REAL,
                status TEXT DEFAULT 'pending',
                vexboost_order_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                invoice_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                amount REAL,
                max_uses INTEGER DEFAULT 1,
                uses INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS promocode_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                promocode_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (promocode_id) REFERENCES promocodes(id)
            )
        ''')
        await db.commit()

async def get_user(user_id: int):
    """Получить пользователя"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return await cursor.fetchone()


async def create_user(user_id: int, username: str = None):
    """Создать пользователя"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            'INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)',
            (user_id, username)
        )
        await db.commit()

async def update_balance(user_id: int, amount: float):
    """Обновить баланс пользователя"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ?',
            (amount, user_id)
        )
        await db.commit()

async def get_balance(user_id: int) -> float:
    """Получить баланс пользователя"""
    user = await get_user(user_id)
    return user['balance'] if user else 0

async def create_order(user_id: int, service_id: str, service_name: str, 
                       quantity: int, price: float):
    """Создать заказ"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            '''INSERT INTO orders (user_id, service_id, service_name, quantity, price)
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, service_id, service_name, quantity, price)
        )
        await db.commit()
        return cursor.lastrowid

async def update_order_status(order_id: int, status: str, vexboost_order_id: str = None):
    """Обновить статус заказа"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if vexboost_order_id:
            await db.execute(
                'UPDATE orders SET status = ?, vexboost_order_id = ? WHERE id = ?',
                (status, vexboost_order_id, order_id)
            )
        else:
            await db.execute(
                'UPDATE orders SET status = ? WHERE id = ?',
                (status, order_id)
            )
        await db.commit()

async def get_user_orders(user_id: int):
    """Получить заказы пользователя"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 10',
            (user_id,)
        )
        return await cursor.fetchall()

async def create_payment(user_id: int, amount: float, invoice_id: str):
    """Создать запись о платеже"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            'INSERT INTO payments (user_id, amount, invoice_id) VALUES (?, ?, ?)',
            (user_id, amount, invoice_id)
        )
        await db.commit()

async def update_payment_status(invoice_id: str, status: str):
    """Обновить статус платежа"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            'UPDATE payments SET status = ? WHERE invoice_id = ?',
            (status, invoice_id)
        )
        await db.commit()

async def get_payment_by_invoice(invoice_id: str):
    """Получить платеж по invoice_id"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM payments WHERE invoice_id = ?',
            (invoice_id,)
        )
        return await cursor.fetchone()


# === Админ функции ===

async def ban_user(user_id: int, banned: bool = True):
    """Забанить/разбанить пользователя"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            'UPDATE users SET banned = ? WHERE user_id = ?',
            (1 if banned else 0, user_id)
        )
        await db.commit()

async def is_banned(user_id: int) -> bool:
    """Проверить бан"""
    user = await get_user(user_id)
    return bool(user and user.get('banned'))

async def get_all_users_count():
    """Количество пользователей"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('SELECT COUNT(*) FROM users')
        row = await cursor.fetchone()
        return row[0] if row else 0

# === Промокоды ===

async def create_promocode(code: str, amount: float, max_uses: int = 1):
    """Создать промокод"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                'INSERT INTO promocodes (code, amount, max_uses) VALUES (?, ?, ?)',
                (code.upper(), amount, max_uses)
            )
            await db.commit()
            return True
        except:
            return False

async def get_promocode(code: str):
    """Получить промокод"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM promocodes WHERE code = ?',
            (code.upper(),)
        )
        return await cursor.fetchone()

async def use_promocode(user_id: int, code: str):
    """Использовать промокод"""
    promo = await get_promocode(code)
    if not promo:
        return None, "Промокод не найден"
    
    if promo['uses'] >= promo['max_uses']:
        return None, "Промокод исчерпан"
    
    # Проверяем, использовал ли уже
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            'SELECT id FROM promocode_uses WHERE user_id = ? AND promocode_id = ?',
            (user_id, promo['id'])
        )
        if await cursor.fetchone():
            return None, "Вы уже использовали этот промокод"
        
        # Используем
        await db.execute(
            'INSERT INTO promocode_uses (user_id, promocode_id) VALUES (?, ?)',
            (user_id, promo['id'])
        )
        await db.execute(
            'UPDATE promocodes SET uses = uses + 1 WHERE id = ?',
            (promo['id'],)
        )
        await db.commit()
    
    await update_balance(user_id, promo['amount'])
    return promo['amount'], "OK"

async def delete_promocode(code: str):
    """Удалить промокод"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('DELETE FROM promocodes WHERE code = ?', (code.upper(),))
        await db.commit()

async def get_all_promocodes():
    """Все промокоды"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM promocodes ORDER BY created_at DESC')
        return await cursor.fetchall()


async def get_user_by_username(username: str):
    """Найти пользователя по username"""
    username = username.lstrip('@').lower()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM users WHERE LOWER(username) = ?',
            (username,)
        )
        return await cursor.fetchone()


async def get_all_users():
    """Получить всех пользователей для рассылки"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT user_id FROM users WHERE banned = 0')
        return await cursor.fetchall()
