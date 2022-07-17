import telebot  # PyTelegramBotAPI
from telebot import types
from pathlib import Path  # to check if some paths exist
from sys import exit  # to stop program if config is not filled
from os import mkdir
import logging  # to log things
import sqlite3  # to make queues of suggested and moderated posts
import configparser  # to use config to set up token etc
import schedule
import threading
import datetime
import time


logging.basicConfig(level=logging.INFO)  # set logger to log all info except telegram debug messages

config = configparser.ConfigParser()  # init configparser
if Path("./config.ini").is_file():
    config.read("./config.ini")
else:

    config.add_section('main')
    config.set('main', 'token', '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11')
    config.set('main', 'channelName', '@mychannel')
    config.set('main', 'moderators', '123456789 987654321 314159265')
    config.set('main', 'begin_time', '12:00')
    config.set('main', 'end_time', '23:00')
    config.set('main', 'posting_interval', '3600')
    config.set('main', 'day_limit', '50')
    logging.warning('No config file was found. Trying to create a new one...')
    try:
        with open("./config.ini", 'w') as configfile:
            config.write(configfile)
    except Exception as e:
        logging.error('Failed to create config file: ', e.__repr__(), e.args)
    else:
        logging.warning('A new config file was created. Fill it with your data and start bot again.')
    exit(0)


token = config.get('main', 'token')  # get bot token
bot = telebot.TeleBot(token, parse_mode='HTML')
channelName = config.get('main', 'channelName')  # channel to post to
moderators = config.get('main', 'moderators').split()  # who can moderate
begin_time = config.get('main', 'begin_time')
end_time = config.get('main', 'end_time')
posting_interval = int(config.get('main', 'posting_interval'))
day_limit = int(config.get('main', 'day_limit'))  # limit of suggestions per day for user

try:  # ascii greeting in console
    from art import *  # pip install art
    tprint('WiseDogeBot')
except ImportError:
    pass


def sqlite_connect():
    conn = sqlite3.connect("db/database.db", check_same_thread=False)
    conn.execute("pragma journal_mode=wal;")
    return conn


def init_sqlite():
    conn = sqlite_connect()
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE SuggestionQueue \
    (id integer primary key, user_id integer, username text, image text, extra text)''')

    cursor.execute('''CREATE TABLE PostQueue \
    (id integer primary key, user_id integer, username text, image text, extra text)''')

    cursor.execute('''CREATE TABLE Stats \
    (id integer primary key, user_id integer, username text, sent integer, sent_today integer, \
    accepted integer, declined integer, is_banned integer)''')
    conn.commit()
    conn.close()
    return


db = Path("./db/database.db")
if not db.is_file():
    logging.warning("Database not found, trying to create a new one...")
    try:
        mkdir('db')
        init_sqlite()
    except Exception as e:
        logging.error("Failed to create database : ", e.__repr__(), e.args)
        pass
    else:
        logging.info("Created database successfully.")


def insert_queue(table: str, user_id: int, username: str, image: str, extra: str):
    # adds an element to suggestion or post queue
    conn = sqlite_connect()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO ' + table + ' (user_id, username, image, extra) VALUES (?,?,?,?)',
        (user_id, username, image, extra)
    )
    conn.commit()


def pop_queue(table: str, image: str):
    conn = sqlite_connect()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ' + table + ' WHERE image = ?', (image,))
    conn.commit()


def run_continuously(interval=1): # auto posting parallel thread
    cease_continuous_run = threading.Event()

    class ScheduleThread(threading.Thread):
        @classmethod
        def run(cls):
            while not cease_continuous_run.is_set():
                schedule.run_pending()
                time.sleep(interval)

    continuous_thread = ScheduleThread()
    continuous_thread.start()
    return cease_continuous_run


def background_job(begin_time, end_time): # post an image when the time comes
    now_time = datetime.datetime.now()  # get current time
    now_time = now_time.strftime('%H:%M')  # convert to string
    # print(begin_time, now_time, end_time)
    if begin_time <= now_time <= end_time:  # check if it in a posting time range
        conn = sqlite_connect()
        cursor = conn.cursor()
        try:
            row = cursor.execute(  # get an image from post queue
                'SELECT user_id, username, image, extra FROM PostQueue ORDER BY id DESC LIMIT 1'
            ).fetchall()[0]  # get first image from post queue
        except IndexError:
            logging.info(now_time + ' - nothing has been posted because of empty post queue. ')
        else:
            bot.send_photo(chat_id=channelName, photo=row[2], caption=row[3])  # send to a channel
            logging.info('{0} - An image with id {1} has been posted.'.format(now_time, row[2]))
            pop_queue('PostQueue', row[2])  # remove image from post queue




schedule.every(posting_interval).seconds.do(background_job, begin_time, end_time)  # start scheduler
stop_run_continuously = run_continuously()


def check_admin(message):
    if str(message.from_user.id) in moderators:
        return True
    return False


@bot.message_handler(commands=["start"])  # handle /start command
def start(message):
    logging.info("User {0}, id{1} entered /start".format(message.from_user.first_name, str(message.from_user.id)))
    markup = make_buttons(message)
    bot.send_message(
        message.chat.id,
        'Здесь ты можешь предложить опубликовать свою мудрость Клыка.\n',
        reply_markup=markup)  # hello message


@bot.message_handler(commands=["stats"])  # show stats
def stats(message):
    conn = sqlite_connect()
    cursor = conn.cursor()
    stats = cursor.execute('SELECT sent, sent_today, accepted, declined, is_banned FROM Stats WHERE user_id = ' +
                           str(message.chat.id)).fetchall()[0]
    bot.send_message(
        message.chat.id,
        'Статистика\nПредложено картинок: {0}\nПредложено сегодня: {1}\nПринято: {2}\nОтклонено: {3}'.format(
        stats[0], stats[1], stats[2], stats[3]
        )
    )
def make_buttons(message):  # makes action buttons
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    item1 = types.KeyboardButton("Предложить")
    markup.add(item1)
    item3 = types.KeyboardButton('Моя статистика')
    markup.add(item3)
    if check_admin(message):
        item2 = types.KeyboardButton("Модерировать")
        markup.add(item2)
    return markup


last_message = ''


@bot.message_handler(content_types=["text"])
def handle_admin_text(message):  # handle actions and moderating
    global user_id, username, image, extra, last_message

    if message.text.strip() == 'Предложить':
        last_message = message.text.strip()
        bot.send_message(message.chat.id, 'Пришли картинку с волком, я добавлю ее в очередь модерации.')
    elif message.text.strip() == 'Моя статистика':
        stats(message)
    elif message.text.strip() == 'Модерировать':
        last_message = message.text.strip()
        if check_admin(message):
            # logging.warning("User {0}, id{1} started moderating".format(
            #     message.from_user.first_name, str(message.from_user.id))
            # )
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)  # add buttons for moderation
            item1 = types.KeyboardButton("+")
            item2 = types.KeyboardButton("-")
            item3 = types.KeyboardButton("Пропуск")
            markup.add(item1)
            markup.add(item2)
            markup.add(item3)

            conn = sqlite_connect()
            cursor = conn.cursor()
            try:
                row = cursor.execute(
                    'SELECT user_id, username, image, extra FROM SuggestionQueue ORDER BY id ASC LIMIT 1'
                    ).fetchall()[0]  # get last image from suggested
            except IndexError:
                bot.send_message(message.chat.id, 'Предложка пуста.')
            else:
                user_id = row[0]  # bad practice, better replace to a dictionary
                username = row[1]
                image = row[2]
                extra = row[3]
                bot.send_photo(message.chat.id, photo=image)
                bot.send_message(
                    message.chat.id,
                    'Картинка от {0} id{1}'.format(username, user_id),
                    reply_markup=markup
                )

        else:
            bot.send_message(message.chat.id, 'Вы не можете модерировать.')
    # handling moderator decision
    elif check_admin(message):
        if message.text.strip() == '+':  # will make bug if moderator sent + without the context of moderating
            # need to check if row exists
            bot.send_message(message.chat.id, 'Добавьте подпись.')
            last_message = message.text.strip()
        elif message.text.strip() == '-':
            last_message = message.text.strip()
            pop_queue(table='SuggestionQueue', image=image)
            markup = make_buttons(message)
            bot.send_message(
                message.chat.id,
                'Картинка снята с модерации.',
                reply_markup=markup
            )

            conn = sqlite_connect()
            cursor = conn.cursor()
            cursor.execute('UPDATE Stats SET declined = declined + 1 WHERE user_id = ' + str(user_id))
            conn.commit()
        elif message.text.strip() == 'Пропуск':  # remove image from queue and add it to the end
            last_message = message.text.strip()
            pop_queue(table='SuggestionQueue', image=image)
            insert_queue(
                table='SuggestionQueue',
                user_id=user_id,
                username=username,
                image=image,
                extra=extra
            )
            markup = make_buttons(message)
            bot.send_message(
                message.chat.id,
                'Картинка перемещена в начало очереди.',
                reply_markup=markup
            )
        elif last_message == '+' and message.text.strip() != last_message:
            insert_queue(
                table='PostQueue',
                user_id=user_id,
                username=username,
                image=image,
                extra='<tg-spoiler>' + message.text.strip() + '</tg-spoiler>'
            )
            markup = make_buttons(message)
            bot.send_message(
                message.chat.id,
                'Картинка добавлена в очередь.',
                reply_markup=markup
            )
            pop_queue(table='SuggestionQueue', image=image)

            conn = sqlite_connect()
            cursor = conn.cursor()
            #is_in_stats = cursor.execute('SELECT EXISTS(SELECT 1 FROM Stats WHERE user_id = ' + str(user_id))
            # if is_in_stats:
            cursor.execute('UPDATE Stats SET accepted = accepted + 1 WHERE user_id = ' + str(user_id))
            conn.commit()
        else:
            logging.debug('Unexpected message: ' + message.text.strip() + ' from user ' + str(message.chat.id))


@bot.message_handler(content_types=['photo'])  # receive an image from user
def handle_photo(message):
    received_image = message.photo[-1].file_id
    logging.info(
        'A photo has just received from user {0}, id {1}'.format(message.from_user.first_name, message.from_user.id))
    insert_queue(
        table='SuggestionQueue',
        user_id=message.from_user.id,
        username=message.from_user.username,
        image=received_image,
        extra=''
    )

    conn = sqlite_connect()
    cursor = conn.cursor()
    is_in_stats = cursor.execute('SELECT EXISTS(SELECT 1 FROM Stats WHERE user_id = ' + str(message.from_user.id) +')').fetchall()[0][0]
    if is_in_stats:
        sent_today = cursor.execute('SELECT sent_today FROM Stats WHERE user_id = ' + \
                                    str(message.from_user.id)).fetchall()[0][0]
        if sent_today <= day_limit:
            cursor.execute('UPDATE Stats SET sent = sent + 1, sent_today = sent_today + 1 WHERE user_id = ' + \
                           str(message.from_user.id))
            conn.commit()
            bot.send_message(message.chat.id, 'Отправил на проверку.')
        else:
            bot.send_message(message.chat.id, 'Вы превысили лимит предложений на сегодня. Попробуйте завтра.')
    else:
        cursor.execute(
            'INSERT INTO Stats (user_id, username, sent, sent_today, accepted, declined, is_banned)\
             VALUES (?,?,?,?,?,?,?)',
            (message.from_user.id, message.from_user.username, 1, 1, 0, 0, 0)
        )
        conn.commit()
        logging.info('Added a new user @' + message.from_user.username + ' in stats.')
        bot.send_message(message.chat.id, 'Отправил на проверку.')


bot.polling(none_stop=True, interval=0)

stop_run_continuously.set()  # scheduler thing
