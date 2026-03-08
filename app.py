import sqlite3
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, g

app = Flask(__name__)
app.secret_key = "optic_pro_system_2026_key"


# ==========================================
# 1. НАСТРОЙКА БАЗЫ ДАННЫХ
# ==========================================

def get_db():
    conn = sqlite3.connect('optics_crm.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    db = get_db()

    # 1. Таблица Оправ
    db.execute("""CREATE TABLE IF NOT EXISTS frames
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, buy_price INTEGER, 
                   sell_price INTEGER, stock INTEGER)""")

    # 2. Таблица Линз
    db.execute("""CREATE TABLE IF NOT EXISTS lenses
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, vision TEXT, lens_type TEXT, 
                   price INTEGER, stock INTEGER)""")

    # 3. Таблица Заказов
    db.execute("""CREATE TABLE IF NOT EXISTS orders
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT, customer_phone TEXT,
                   frame_id INTEGER, lens_id_right INTEGER, lens_id_left INTEGER, pd TEXT,
                   total_price INTEGER, status TEXT, date TEXT, is_updated INTEGER DEFAULT 0)""")

    # Попытка добавить колонку, если её нет
    try:
        db.execute("ALTER TABLE orders ADD COLUMN is_updated INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # 4. Таблица Финансов
    db.execute("""CREATE TABLE IF NOT EXISTS finance
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, amount INTEGER, 
                   description TEXT, date TEXT)""")

    # 5. ТАБЛИЦА АКСЕССУАРОВ (Прочие товары) - ТЕПЕРЬ ОНА ТОЧНО СОЗДАСТСЯ
    db.execute("""CREATE TABLE IF NOT EXISTS accessories
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                   category TEXT NOT NULL, 
                   name TEXT NOT NULL, 
                   price INTEGER NOT NULL, 
                   stock INTEGER NOT NULL)""")

    # 6. Журнал активности сотрудников
    db.execute("""CREATE TABLE IF NOT EXISTS activity_log
                  (
                      id
                      INTEGER
                      PRIMARY
                      KEY
                      AUTOINCREMENT,
                      user_role
                      TEXT,
                      action
                      TEXT,
                      details
                      TEXT,
                      date
                      TEXT
                  )""")

    db.commit()
    db.close()
    print("✅ База данных успешно инициализирована!")

# ОБЯЗАТЕЛЬНО ВЫЗЫВАЕМ ЭТУ ФУНКЦИЮ ПОСЛЕ ОПРЕДЕЛЕНИЯ
init_db()

def log_action(user_role, action, details):
    db = get_db()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT INTO activity_log (user_role, action, details, date) VALUES (?, ?, ?, ?)",
               (user_role, action, details, current_time))
    db.commit()
    db.close()

# Фильтр для красивых цен (1 000 000)
@app.template_filter('format_price')
def format_price(value):
    try:
        return "{:,.0f}".format(float(value)).replace(",", " ")
    except:
        return "0"


@app.template_filter('number_format')
def number_format(value):
    return format_price(value)


# Глобальные уведомления (доступны везде)
@app.context_processor
def inject_notifications():
    try:
        db = get_db()
        low_f = db.execute("SELECT * FROM frames WHERE stock <= 5").fetchall()
        low_l = db.execute("SELECT * FROM lenses WHERE stock <= 5").fetchall()
        count = len(low_f) + len(low_l)
        db.close()
        return dict(low_stock_count=count, low_frames_list=low_f, low_lenses_list=low_l)
    except:
        return dict(low_stock_count=0, low_frames_list=[], low_lenses_list=[])


# ==========================================
# 2. АВТОРИЗАЦИЯ
# ==========================================

def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_role' not in session:
                return redirect(url_for('login'))
            if role and session.get('user_role') != role and session.get('user_role') != 'manager':
                return "Доступ запрещен", 403
            return f(*args, **kwargs)

        return decorated_function

    return decorator


@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Простой вход по паролю (можно усложнить)
        username = request.form.get('username')
        password = request.form.get('password')

        users = {
            "seller": ("1234", "seller"),
            "master": ("4321", "master"),
            "manager": ("admin", "manager")
        }

        if username in users and users[username][0] == password:
            session['user_role'] = users[username][1]
            return redirect(url_for(f"{session['user_role']}_dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ==========================================
# 3. ПРОДАВЕЦ (SELLER)
# ==========================================

@app.route("/seller")
@login_required("seller")
def seller_dashboard():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    # Считаем приход за сегодня
    income = db.execute(
        "SELECT SUM(amount) FROM finance WHERE type = 'приход' AND date = ?", (today,)
    ).fetchone()[0] or 0

    # Считаем расходы за сегодня
    expense = db.execute(
        "SELECT SUM(amount) FROM finance WHERE type = 'расход' AND date = ?", (today,)
    ).fetchone()[0] or 0

    db.close()
    return render_template("seller_dashboard.html", income=income, expense=expense)


# --- СПИСОК ПРОЧИХ ТОВАРОВ ---
@app.route("/seller/other")
@login_required("seller")
def other_items():
    db = get_db()
    search = request.args.get('search', '')
    query = "SELECT * FROM accessories WHERE name LIKE ? OR category LIKE ? ORDER BY category ASC"
    items = db.execute(query, (f"%{search}%", f"%{search}%")).fetchall()
    db.close()
    return render_template("other_items.html", items=items, search_query=search)


# --- ДОБАВЛЕНИЕ ---
@app.route("/seller/other/add", methods=["POST"])
@login_required("seller")
def add_other_item():
    db = get_db()
    category = request.form.get('category')
    name = request.form.get('name')
    price = request.form.get('price')
    stock = request.form.get('stock')

    db.execute("INSERT INTO accessories (category, name, price, stock) VALUES (?, ?, ?, ?)",
               (category, name, price, stock))
    db.commit()
    db.close()
    return redirect("/seller/other")


# --- РЕДАКТИРОВАНИЕ ---
@app.route("/seller/other/edit/<int:id>", methods=["POST"])
@login_required("seller")
def edit_other_item(id):
    db = get_db()
    db.execute("""
               UPDATE accessories
               SET category=?,
                   name=?,
                   price=?,
                   stock=?
               WHERE id = ?
               """, (request.form.get('category'), request.form.get('name'),
                     request.form.get('price'), request.form.get('stock'), id))
    db.commit()
    db.close()
    return redirect("/seller/other")


@app.route("/seller/other/sell", methods=["POST"])
@login_required("seller")
def sell_other_manual():
    db = get_db()

    # Получаем данные из формы
    item_name = request.form.get('name')  # Что продали (например, "Футляр")
    price = int(request.form.get('price'))  # За сколько продали
    qty = int(request.form.get('qty'))  # Сколько штук

    total = price * qty
    today = datetime.now().strftime("%Y-%m-%d")

    # Записываем в финансы как ПРИХОД
    db.execute("""
               INSERT INTO finance (type, amount, description, date)
               VALUES ('приход', ?, ?, ?)
               """, (total, f"Прочее: {item_name} ({qty} шт.)", today))

    db.commit()
    db.close()

    # Возвращаемся на главную, где обновится карточка "Прибыль"
    return redirect(url_for('seller_dashboard'))

# --- УДАЛЕНИЕ ---
@app.route("/seller/other/delete/<int:id>")
@login_required("seller")
def delete_other_item(id):
    db = get_db()
    db.execute("DELETE FROM accessories WHERE id = ?", (id,))
    db.commit()
    db.close()
    return redirect("/seller/other")
@app.route("/seller/frames")
@login_required("seller")
def frames_list():
    db = get_db()
    # Получаем текст из поля поиска (если он есть)
    search_query = request.args.get('search', '').strip()

    if search_query:
        # Используем оператор LIKE для поиска по части названия
        # % слово % означает, что ищем совпадение в любом месте строки
        query = "SELECT * FROM frames WHERE name LIKE ? ORDER BY name ASC"
        frames = db.execute(query, (f"%{search_query}%",)).fetchall()
    else:
        # Если поиска нет, просто выводим все оправы
        frames = db.execute("SELECT * FROM frames ORDER BY id DESC").fetchall()

    db.close()
    return render_template("seller_frames.html", frames=frames, search_query=search_query)


@app.route("/seller/frames/add", methods=["GET", "POST"])
@login_required("seller")
def add_frame():
    if request.method == "POST":
        db = get_db()
        db.execute("INSERT INTO frames (name, buy_price, sell_price, stock) VALUES (?,?,?,?)",
                   (request.form['name'], request.form['buy_price'], request.form['sell_price'], request.form['stock']))
        db.commit()
        db.close()
        return redirect(url_for('frames_list'))
    return render_template("add_frame.html")


# --- ШАГ 1: СОЗДАНИЕ ЗАКАЗА (ПРОДАВЕЦ) ---
@app.route("/seller/order/add", methods=["GET", "POST"])
@login_required("seller")
def add_order():
    db = get_db()
    if request.method == "POST":
        try:
            customer = request.form.get('customer_name')
            phone = request.form.get('customer_phone')
            f_name = request.form.get('frame_name')
            l_name_r = request.form.get('lens_name_right')
            l_name_l = request.form.get('lens_name_left')
            pd_val = request.form.get('pd', '64')

            frame = db.execute("SELECT id, sell_price FROM frames WHERE name = ?", (f_name,)).fetchone()
            lens_r = db.execute("SELECT id, price FROM lenses WHERE (vision || ' ' || lens_type) = ?",
                                (l_name_r,)).fetchone()
            lens_l = db.execute("SELECT id, price FROM lenses WHERE (vision || ' ' || lens_type) = ?",
                                (l_name_l,)).fetchone()

            if not frame or not lens_r or not lens_l:
                return "Ошибка: Товар не найден", 400

            # Кассовый расчет (30к — наценка магазина)
            total_income = frame['sell_price'] + lens_r['price'] + lens_l['price'] + 30000
            now_full = datetime.now().strftime("%Y-%m-%d %H:%M")
            now_date = datetime.now().strftime("%Y-%m-%d")

            # 1. Сохраняем заказ в базу
            db.execute("""INSERT INTO orders (customer_name, customer_phone, frame_id, lens_id_right, lens_id_left, pd,
                                              total_price, status, date)
                          VALUES (?, ?, ?, ?, ?, ?, ?, 'Новый', ?)""",
                       (customer, phone, frame['id'], lens_r['id'], lens_l['id'], pd_val, total_income, now_full))

            # 2. Списываем товар со склада
            db.execute("UPDATE frames SET stock = stock - 1 WHERE id = ?", (frame['id'],))
            db.execute("UPDATE lenses SET stock = stock - 1 WHERE id IN (?, ?)", (lens_r['id'], lens_l['id']))

            # 3. ФИНАНСЫ: ПРИХОД (Деньги в кассу от клиента)
            db.execute("INSERT INTO finance (type, amount, description, date) VALUES ('приход', ?, ?, ?)",
                       (total_income, f"Заказ: {customer}", now_date))

            # ЗП мастера ТУТ УДАЛЕНА. Она будет в другой функции.

            db.commit()
            return redirect(url_for('seller_dashboard'))
        finally:
            db.close()

    frames = db.execute("SELECT * FROM frames WHERE stock > 0").fetchall()
    lenses = db.execute("SELECT * FROM lenses WHERE stock > 0").fetchall()
    return render_template("add_order.html", frames=frames, lenses=lenses)


# --- ШАГ 2: ЗАВЕРШЕНИЕ ЗАКАЗА (МАСТЕР) ---
@app.route("/master/order/complete/<int:order_id>")
@login_required("master")
def complete_order(order_id):
    db = get_db()
    try:
        order = db.execute("SELECT customer_name FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order:
            # 1. Меняем статус заказа на 'Готово'
            db.execute("UPDATE orders SET status = 'Готово' WHERE id = ?", (order_id,))

            # 2. ФИНАНСЫ: ЗП МАСТЕРА (РОВНО 20 000 ЗА ФАКТ РАБОТЫ)
            today = datetime.now().strftime("%Y-%m-%d")
            db.execute("""INSERT INTO finance (type, amount, description, date)
                          VALUES ('расход', 20000, ?, ?)""",
                       (f"ЗП Мастера (Готов заказ): {order['customer_name']}", today))

            db.commit()
    finally:
        db.close()
    return redirect("/master/orders")
@app.route("/seller/orders")
@login_required("seller")
def seller_orders_list():
    db = get_db()

    # Получаем дату из ссылки (например, /seller/orders?date=2026-03-06)
    # Если даты в ссылке нет, берем сегодняшнюю по умолчанию
    selected_date = request.args.get('date')
    today = datetime.now().strftime("%Y-%m-%d")

    if selected_date:
        # Фильтруем заказы по конкретной дате
        query = """
                SELECT o.*, f.name as frame_name
                FROM orders o
                         JOIN frames f ON o.frame_id = f.id
                WHERE o.date LIKE ?
                ORDER BY o.id DESC \
                """
        orders = db.execute(query, (f"{selected_date}%",)).fetchall()
        title = f"Заказы за {selected_date}"
    else:
        # Если дата не указана, показываем вообще всё (или только сегодня - на твой выбор)
        # Давай сделаем, чтобы по умолчанию показывал только СЕГОДНЯ
        query = """
                SELECT o.*, f.name as frame_name
                FROM orders o
                         JOIN frames f ON o.frame_id = f.id
                WHERE o.date LIKE ?
                ORDER BY o.id DESC \
                """
        orders = db.execute(query, (f"{today}%",)).fetchall()
        title = "Заказы за сегодня"

    db.close()
    return render_template("seller_orders.html", orders=orders, title=title)


@app.route("/seller/history")
@login_required("seller")
def seller_history():
    db = get_db()
    # Этот запрос берет все записи из finance (и заказы, и прочее)
    # и группирует их по дням, чтобы показать общую выручку за день
    query = """
            SELECT
                date as day_date, SUM (amount) as day_total, COUNT (*) as operations_count
            FROM finance
            WHERE type = 'приход'
            GROUP BY date
            ORDER BY date DESC \
            """
    history = db.execute(query).fetchall()

    # Также берем ВСЕ детальные записи для списка ниже (если захочешь вывести всё сразу)
    all_records = db.execute("""
                             SELECT *
                             FROM finance
                             WHERE type = 'приход'
                             ORDER BY id DESC LIMIT 50
                             """).fetchall()

    db.close()
    return render_template("seller_history.html", history=history, all_records=all_records,
                           today=datetime.now().strftime("%Y-%m-%d"))


@app.route("/seller/history/detail/<date>")
@login_required("seller")
def seller_history_detail(date):
    db = get_db()
    # Берем все операции (приходы и расходы) именно за выбранную дату
    records = db.execute("""
                         SELECT *
                         FROM finance
                         WHERE date = ?
                         ORDER BY id DESC
                         """, (date,)).fetchall()

    # Считаем итог за день для заголовка
    day_total = db.execute("SELECT SUM(amount) FROM finance WHERE date = ? AND type = 'приход'", (date,)).fetchone()[
                    0] or 0

    db.close()
    return render_template("finance_detail.html", records=records, date=date, day_total=day_total)


@app.route("/fix_history_with_phones")
def fix_history_with_phones():
    db = get_db()
    # Берем данные из заказов, включая телефон
    orders = db.execute("SELECT customer_name, customer_phone, total_price, date FROM orders").fetchall()

    for order in orders:
        desc = f"Заказ: {order['customer_name']} | Тел: {order['customer_phone']}"
        # Проверяем, нет ли уже такой записи (по имени и дате)
        exists = db.execute("SELECT id FROM finance WHERE description LIKE ?",
                            (f"Заказ: {order['customer_name']}%",)).fetchone()

        if not exists:
            db.execute("INSERT INTO finance (type, amount, description, date) VALUES ('приход', ?, ?, ?)",
                       (order['total_price'], desc, order['date']))
        else:
            # Если запись есть, но без телефона — обновляем её
            db.execute("UPDATE finance SET description = ? WHERE id = ?", (desc, exists['id']))

    db.commit()
    db.close()
    return "История обновлена: Имена и Телефоны добавлены в финансы!"


@app.route("/fix_names")
def fix_names():
    db = get_db()
    # Берем данные из таблицы заказов
    orders = db.execute("SELECT customer_name, customer_phone, total_price, date FROM orders").fetchall()

    for order in orders:
        new_desc = f"Заказ: {order['customer_name']} | Тел: {order['customer_phone']}"
        # Ищем запись в финансах по дате и сумме, чтобы обновить описание
        db.execute("""
                   UPDATE finance
                   SET description = ?
                   WHERE date = ? AND amount = ? AND description LIKE 'Заказ:%'
                   """, (new_desc, order['date'], order['total_price']))

    db.commit()
    db.close()
    return "Имена и телефоны успешно перенесены в историю финансов!"
# ==========================================
# 4. МАСТЕР (MASTER)
# ==========================================

@app.route("/master")
@login_required("master")
def master_dashboard():
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        # 1. ЗАРПЛАТА ЗА СЕГОДНЯ
        income_row = db.execute("""
                                SELECT SUM(amount)
                                FROM finance
                                WHERE type = 'расход'
                                  AND description LIKE 'ЗП Мастера%'
                                  AND date = ?
                                """, (today,)).fetchone()
        income_today = income_row[0] if income_row and income_row[0] else 0

        # 2. ИСТОРИЯ РАБОТ
        history = db.execute("""
                             SELECT amount, description
                             FROM finance
                             WHERE type = 'расход'
                               AND description LIKE 'ЗП Мастера%'
                               AND date = ?
                             ORDER BY id DESC
                             """, (today,)).fetchall()

        # 3. КОЛИЧЕСТВО ЗАКАЗОВ В ОЧЕРЕДИ
        orders_count = db.execute("SELECT COUNT(*) FROM orders WHERE status != 'Готово'").fetchone()[0]

        # 4. ДЕФИЦИТ (ТО, ЧТО ВЫЗЫВАЛО ОШИБКУ)
        low_lenses = db.execute("SELECT vision, stock FROM lenses WHERE stock <= 6").fetchall()
        low_frames = db.execute("SELECT name, stock FROM frames WHERE stock <= 2").fetchall()
        low_stock_count = len(low_lenses) + len(low_frames)

    except Exception as e:
        print(f"Ошибка в мастере: {e}")
        income_today, history, orders_count, low_lenses, low_frames, low_stock_count = 0, [], 0, [], [], 0
    finally:
        db.close()

    return render_template("master_dashboard.html",
                           income_today=income_today,
                           history=history,
                           orders_count=orders_count,
                           low_lenses=low_lenses,
                           low_frames=low_frames,
                           low_stock_count=low_stock_count)
@app.route("/master/orders")
@login_required("master")
def master_orders():
    db = get_db()
    # ВНИМАНИЕ: Проверь, чтобы перед FROM не было лишней запятой!
    query = """
        SELECT 
            o.id, 
            o.customer_name, 
            o.status, 
            o.pd,
            f.name as f_name,
            lr.vision as vision_right,
            ll.vision as vision_left
        FROM orders o
        JOIN frames f ON o.frame_id = f.id
        JOIN lenses lr ON o.lens_id_right = lr.id
        JOIN lenses ll ON o.lens_id_left = ll.id
        WHERE o.status != 'Готово'
    """
    try:
        orders = db.execute(query).fetchall()
        db.close()
        return render_template("master_orders.html", orders=orders)
    except Exception as e:
        db.close()
        return f"Ошибка в базе данных: {e}", 500
@app.route("/master/lenses/add", methods=["GET", "POST"])
@login_required("master")
def add_lens():
    if request.method == "POST":
        db = get_db()
        vision = request.form['vision'].strip()
        lens_type = request.form['lens_type'].strip()
        price = request.form['price']
        new_stock = int(request.form['stock'])

        # Ищем, есть ли уже такая линза (совпадение диоптрии и типа)
        existing = db.execute(
            "SELECT id, stock FROM lenses WHERE vision = ? AND lens_type = ?",
            (vision, lens_type)
        ).fetchone()

        if existing:
            # Если нашли — ПРИБАВЛЯЕМ к остатку
            db.execute(
                "UPDATE lenses SET stock = stock + ?, price = ? WHERE id = ?",
                (new_stock, price, existing['id'])
            )
        else:
            # Если не нашли — СОЗДАЕМ новую строку
            db.execute("""
                       INSERT INTO lenses (vision, lens_type, price, stock)
                       VALUES (?, ?, ?, ?)
                       """, (vision, lens_type, price, new_stock))

        db.commit()
        db.close()
        return redirect(url_for('master_lenses'))

    return render_template("add_lens.html")
@app.route("/master/order/work/<int:oid>", methods=["POST"])
def master_work(oid):
    db = get_db()
    # Статус меняется + ставим метку для продавца
    db.execute("UPDATE orders SET status='В работе', is_updated=1 WHERE id=?", (oid,))
    db.commit()
    db.close()
    return redirect(url_for('master_orders'))


@app.route("/master/order/done/<int:oid>", methods=["POST"])
@login_required("master")
def master_done(oid):
    db = get_db()

    # 1. Сначала находим информацию о заказе (сумму и имя клиента)
    order = db.execute("SELECT total_price, customer_name FROM orders WHERE id=?", (oid,)).fetchone()

    if order:
        # 2. Меняем статус заказа на 'Готово' и ставим уведомление
        db.execute("UPDATE orders SET status='Готово', is_updated=1 WHERE id=?", (oid,))

        # 3. ДОБАВЛЯЕМ ДЕНЬГИ В ТАБЛИЦУ ФИНАНСОВ
        # Теперь выручка появится в отчетах!
        db.execute("""
                   INSERT INTO finance (type, amount, description, date)
                   VALUES ('приход', ?, ?, ?)
                   """, (
                       order['total_price'],
                       f"Выполнен заказ №{oid}: {order['customer_name']}",
                       datetime.now().strftime("%Y-%m-%d")
                   ))

        db.commit()
        print(f"✅ Заказ №{oid} готов, выручка {order['total_price']} записана!")

    db.close()
    return redirect(url_for('master_orders_list'))
@app.route("/master/lenses")
@login_required("master")
def master_lenses():
    db = get_db()
    search = request.args.get('search', '')
    query = "SELECT * FROM lenses WHERE vision LIKE ? ORDER BY stock ASC"
    lenses = db.execute(query, (f"%{search}%",)).fetchall()
    db.close()
    return render_template("master_lenses.html", lenses=lenses)


@app.route("/master/orders")
@login_required("master")
def master_orders_list():  # имя функции может быть любым
    db = get_db()
    # Важно: JOIN-ы должны быть правильными, чтобы f_name и vision_right существовали
    query = """
            SELECT o.*, f.name as f_name, lr.vision as vision_right, ll.vision as vision_left
            FROM orders o
                     JOIN frames f ON o.frame_id = f.id
                     JOIN lenses lr ON o.lens_id_right = lr.id
                     JOIN lenses ll ON o.lens_id_left = ll.id
            WHERE o.status IN ('Новый', 'В работе')
            ORDER BY o.id DESC \
            """
    orders = db.execute(query).fetchall()
    db.close()

    # ПРОВЕРЬ ТУТ: имя переменной должно быть 'orders' (во множественном числе)
    return render_template("master_orders.html", orders=orders)
# ==========================================
# 5. МЕНЕДЖЕР (MANAGER)
# ==========================================

@app.route("/manager/dashboard")
@login_required("manager")
def manager_dashboard():
    db = get_db()
    try:
        # 1. ФИНАНСЫ
        total_income = db.execute("SELECT SUM(amount) FROM finance WHERE type = 'приход'").fetchone()[0] or 0
        total_investments = db.execute("SELECT SUM(amount) FROM finance WHERE type = 'вложение'").fetchone()[0] or 0
        total_expenses = db.execute("SELECT SUM(amount) FROM finance WHERE type = 'расход'").fetchone()[0] or 0
        total_cogs = db.execute("""
            SELECT SUM(f.buy_price) FROM orders o JOIN frames f ON o.frame_id = f.id
        """).fetchone()[0] or 0

        # 2. ОСТАТКИ (Оправы <= 2, Линзы <= 6 штук)
        low_f = db.execute("SELECT name, stock FROM frames WHERE stock <= 2").fetchall()
        low_l = db.execute("SELECT (vision || ' ' || lens_type) as name, stock FROM lenses WHERE stock <= 6").fetchall()
        low_stock = list(low_f) + list(low_l)

        # 3. МАТЕМАТИКА
        net_profit = total_income - total_expenses - total_cogs
        cash_on_hand = (total_income + total_investments) - total_expenses
        active_orders_count = db.execute("SELECT COUNT(*) FROM orders WHERE status != 'Готово'").fetchone()[0]

        # 4. ЛОГИ
        try:
            logs = list(db.execute("SELECT * FROM activity_log ORDER BY id DESC LIMIT 10").fetchall())
        except:
            logs = []

    finally:
        db.close()

    return render_template("manager_dashboard.html",
                           income=total_income, investments=total_investments,
                           expenses=total_expenses, net_profit=net_profit,
                           cash_on_hand=cash_on_hand, low_stock=low_stock,
                           active_orders_count=active_orders_count, logs=logs)
# ФУНКЦИЯ ДЛЯ ВЛОЖЕНИЙ И РАСХОДОВ
@app.route("/manager/finance/action", methods=["POST"])
@login_required("manager")
def manager_finance_action():
    db = get_db()
    try:
        amount = int(request.form.get('amount'))
        description = request.form.get('description')
        action_type = request.form.get('action_type')  # 'расход' или 'вложение'
        date = datetime.now().strftime("%Y-%m-%d")

        # 1. Записываем в финансовую таблицу
        db.execute("INSERT INTO finance (type, amount, description, date) VALUES (?, ?, ?, ?)",
                   (action_type, amount, description, date))
        db.commit()

        # 🕵️‍♂️ ШПИОН: Фиксируем движение денег в журнале активности
        # Чтобы ты видел в ленте: "Менеджер | Касса: расход | Сумма: 50,000 (Аренда)"
        log_action("Менеджер", f"Касса: {action_type}", f"Сумма: {amount:,} сум. Причина: {description}")

    except Exception as e:
        print(f"Ошибка в финансах: {e}")
    finally:
        db.close()

    return redirect(url_for('manager_dashboard'))
# ФУНКЦИЯ ДОБАВЛЕНИЯ РАСХОДА МЕНЕДЖЕРОМ
@app.route("/manager/add_expense", methods=["POST"])
@login_required("manager")
def add_expense():
    db = get_db()
    amount = int(request.form.get('amount'))
    description = request.form.get('description')  # Например: "Аренда за март"
    date = datetime.now().strftime("%Y-%m-%d")

    db.execute("INSERT INTO finance (type, amount, description, date) VALUES ('расход', ?, ?, ?)",
               (amount, description, date))
    db.commit()
    db.close()
    return redirect(url_for('manager_dashboard'))
@app.route("/manager/stats")
@login_required("manager")
def manager_stats():
    db = get_db()
    # Считаем сумму всех приходов
    total_income = db.execute("SELECT SUM(amount) FROM finance WHERE type='приход'").fetchone()[0] or 0
    # Считаем сумму всех расходов
    total_expense = db.execute("SELECT SUM(amount) FROM finance WHERE type='расход'").fetchone()[0] or 0

    profit = total_income - total_expense

    db.close()
    return render_template("manager_stats.html", income=total_income, expense=total_expense, profit=profit)


@app.route("/master/earnings")
@login_required("master")
def master_earnings():
    db = get_db()
    # Берем текущую дату без времени для сравнения
    today = datetime.now().strftime("%Y-%m-%d")
    FIXED_RATE = 20000

    # 1. Заказы за СЕГОДНЯ (используем LIKE, чтобы найти все за это число независимо от времени)
    today_orders = db.execute("""
                              SELECT o.*, f.name as frame_name
                              FROM orders o
                                       JOIN frames f ON o.frame_id = f.id
                              WHERE o.status = 'Готово'
                                AND o.date LIKE ?
                              """, (f"{today}%",)).fetchall()

    today_count = len(today_orders)
    today_earnings = today_count * FIXED_RATE

    # 2. ИСТОРИЯ (Группируем, обрезая время)
    # SUBSTR(date, 1, 10) берет только "YYYY-MM-DD"
    history = db.execute("""
                         SELECT SUBSTR(date, 1, 10) as day_date, COUNT(id) as count
                         FROM orders
                         WHERE status = 'Готово' AND date NOT LIKE ?
                         GROUP BY day_date
                         ORDER BY day_date DESC
                         """, (f"{today}%",)).fetchall()

    db.close()
    return render_template("master_earnings.html",
                           today_orders=today_orders,
                           today_count=today_count,
                           today_earnings=today_earnings,
                           history=history,
                           rate=FIXED_RATE,
                           today=today)


@app.route("/master/earnings/day/<date_str>")
@login_required("master")
def master_earnings_day(date_str):
    db = get_db()
    FIXED_RATE = 20000

    # Используем LIKE '2026-03-06%', чтобы найти все заказы за этот день
    orders = db.execute("""
                        SELECT o.*, f.name as frame_name
                        FROM orders o
                                 JOIN frames f ON o.frame_id = f.id
                        WHERE o.status = 'Готово'
                          AND o.date LIKE ?
                        """, (f"{date_str}%",)).fetchall()

    total_day_money = len(orders) * FIXED_RATE
    db.close()

    return render_template("master_day_detail.html",
                           orders=orders,
                           date=date_str,
                           total_money=total_day_money)

# --- УДАЛЕНИЕ ЛИНЗЫ ---
@app.route("/master/lens/delete/<int:id>")
@login_required("master")
def delete_lens(id):
    db = get_db()
    db.execute("DELETE FROM lenses WHERE id = ?", (id,))
    db.commit()
    db.close()
    # Возвращаем на страницу списка линз мастера
    return redirect("/master/lenses")


# --- УДАЛЕНИЕ ОПРАВЫ ---
@app.route("/master/frame/delete/<int:id>")
@login_required("master")
def delete_frame(id):
    db = get_db()
    db.execute("DELETE FROM frames WHERE id = ?", (id,))
    db.commit()
    db.close()
    # Возвращаем на страницу склада оправ (проверь свой путь, обычно это /seller/frames)
    return redirect("/seller/frames")


# --- РЕДАКТИРОВАНИЕ ОПРАВЫ (POST запрос) ---
@app.route("/seller/frames/edit/<int:id>", methods=["POST"])
@login_required("seller")
def edit_frame(id):
    db = get_db()
    # Получаем новые данные из полей модального окна
    name = request.form.get('name')
    price = request.form.get('price')
    stock = request.form.get('stock')

    # Обновляем базу данных
    db.execute("""
               UPDATE frames
               SET name       = ?,
                   sell_price = ?,
                   stock      = ?
               WHERE id = ?
               """, (name, price, stock, id))

    db.commit()
    db.close()

    # Возвращаемся обратно на склад по прямому адресу
    return redirect("/seller/frames")


@app.route("/master/lens/edit/<int:lens_id>", methods=["POST"])
@login_required("master")
def edit_lens_master(lens_id):
    db = get_db()
    new_stock = request.form.get('stock')

    # 🕵️‍♂️ ШПИОН: Узнаем старое количество перед обновлением
    old_data = db.execute("SELECT vision, stock FROM lenses WHERE id=?", (lens_id,)).fetchone()

    if new_stock is not None:
        db.execute("UPDATE lenses SET stock = ? WHERE id = ?", (new_stock, lens_id))
        db.commit()

        # 🕵️‍♂️ ШПИОН: Записываем действие в журнал
        log_action("Мастер", "Изменение склада",
                   f"Линза {old_data['vision']}: было {old_data['stock']} шт, стало {new_stock} шт")

    db.close()
    return "Success", 200


@app.route("/manager/sales_report")
@login_required("manager")
def sales_report():
    db = get_db()
    period = request.args.get('period', 'day')
    now = datetime.now()

    # Логика фильтра дат
    if period == 'day':
        start_date = now.strftime("%Y-%m-%d")
    elif period == 'week':
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    elif period == 'month':
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    else:
        start_date = "2000-01-01"

    try:
        # 1. Склад (для блоков вверху)
        frames_stock = db.execute("SELECT name, stock FROM frames").fetchall()
        lenses_stock = db.execute("SELECT vision, lens_type, stock FROM lenses").fetchall()
        total_frames = sum(f['stock'] for f in frames_stock)
        total_lenses = sum(l['stock'] for l in lenses_stock)

        # 2. Продажи и расчет прибыли
        sales = db.execute("""
                           SELECT o.id,
                                  o.customer_name,
                                  o.total_price                         as sell_price,
                                  o.date,
                                  f.name                                as frame_name,
                                  f.buy_price                           as frame_cost,
                                  (o.total_price - f.buy_price - 20000) as net_profit
                           FROM orders o
                                    JOIN frames f ON o.frame_id = f.id
                           WHERE o.date >= ?
                           ORDER BY o.id DESC
                           """, (start_date,)).fetchall()

        # 3. Итоги (ВАЖНО: эти переменные ищет твой HTML)
        total_revenue = sum(s['sell_price'] for s in sales) if sales else 0
        total_costs = sum(s['frame_cost'] for s in sales) if sales else 0
        total_master_fees = len(sales) * 20000
        net_profit = total_revenue - total_costs - total_master_fees

    finally:
        db.close()

    # Передаем ВСЕ переменные, чтобы не было ошибки Undefined
    return render_template("sales_report.html",
                           sales=sales,
                           frames=frames_stock,
                           lenses=lenses_stock,
                           total_frames=total_frames,
                           total_lenses=total_lenses,
                           total_revenue=total_revenue,  # Ошибка была тут
                           net_profit=net_profit,
                           current_period=period)

@app.route("/order/print/<int:order_id>")
@login_required("seller")  # Или "manager"
def print_receipt(order_id):
    db = get_db()
    # Собираем все данные заказа, объединяя таблицы
    order = db.execute("""
                       SELECT o.*,
                              f.name       as frame_name,
                              lr.vision    as vision_r,
                              lr.lens_type as type_r,
                              ll.vision    as vision_l,
                              ll.lens_type as type_l
                       FROM orders o
                                JOIN frames f ON o.frame_id = f.id
                                JOIN lenses lr ON o.lens_id_right = lr.id
                                JOIN lenses ll ON o.lens_id_left = ll.id
                       WHERE o.id = ?
                       """, (order_id,)).fetchone()
    db.close()

    if not order:
        return "Заказ не найден", 404

    return render_template("print_receipt.html", order=order)


@app.route("/manager/full_report")
@login_required("manager")
def full_report():
    db = get_db()

    # 1. ОТЧЕТ ПО ОПРАВАМ (Остатки и стоимость склада)
    frames_stock = db.execute(
        "SELECT name, stock, buy_price, (stock * buy_price) as total_value FROM frames").fetchall()
    total_frames_count = sum(f['stock'] for f in frames_stock)

    # 2. ОТЧЕТ ПО ЛИНЗАМ
    lenses_stock = db.execute(
        "SELECT vision, lens_type, stock, buy_price, (stock * buy_price) as total_value FROM lenses").fetchall()
    total_lenses_count = sum(l['stock'] for l in lenses_stock)

    # 3. ПРИБЫЛЬ ЗА МЕСЯЦ
    month_start = datetime.now().strftime("%Y-%m-01")
    sales = db.execute("""
                       SELECT SUM(amount)
                       FROM finance
                       WHERE type = 'приход' AND date >= ?
                       """, (month_start,)).fetchone()[0] or 0

    costs = db.execute("""
                       SELECT SUM(amount)
                       FROM finance
                       WHERE type = 'расход' AND date >= ?
                       """, (month_start,)).fetchone()[0] or 0

    db.close()
    return render_template("manager_report.html",
                           frames=frames_stock,
                           lenses=lenses_stock,
                           total_frames=total_frames_count,
                           total_lenses=total_lenses_count,
                           net_profit=(sales - costs))




# ==========================================
# ЗАПУСК
# ==========================================

if __name__ == "__main__":
    # Для локального запуска (у тебя на ПК)
    # app.run(debug=True)
    
    # Для работы на сервере (Render/VPS)
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
