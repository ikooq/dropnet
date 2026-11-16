"""Complaint templates (Russian) with English twins.

Campaign scripts are deliberately distinctive: a gang re-uses its own script.
Generic templates are used for unrelated (noise) complaints of the same tactic.
Placeholders: {phone} {phone2} {card} {card2} {iban} {url} {amount} {name} {hub}
"""
from __future__ import annotations

# (ru, en) pairs
Template = tuple[str, str]

CAMPAIGN_SCRIPTS: dict[str, list[Template]] = {
    # A: shared mule card, fake bank security
    "BANK_SECURITY": [
        ("Мне позвонили с номера {phone}, представились Ерланом из отдела финансового мониторинга. "
         "Сказали, что из Шымкента пытаются оформить кредит на моё имя, и чтобы его отменить, нужно "
         "перевести деньги на резервную карту банка {card}. Я перевела {amount}.",
         "A caller from {phone} said he was Erlan from the bank's financial monitoring unit. He claimed "
         "someone in Shymkent was taking a loan in my name and that I had to move money to the bank's "
         "reserve card {card} to cancel it. I sent {amount}."),
        ("Звонок с {phone}: «Ерлан, отдел финансового мониторинга». Сообщил, что на меня оформляют кредит "
         "из Шымкента, велел срочно перевести средства на резервную карту {card}. Перевёл {amount}, "
         "после этого номер недоступен.",
         "Call from {phone}: 'Erlan, financial monitoring'. Said a loan from Shymkent was being taken in "
         "my name and told me to urgently move funds to reserve card {card}. I sent {amount}; the number "
         "went dead afterwards."),
        ("Позвонил якобы сотрудник финансового мониторинга банка Ерлан ({phone}). Про попытку кредита из "
         "Шымкента. Попросил перевести деньги на резервную карту {card} для защиты. Ущерб {amount}.",
         "A so-called bank financial-monitoring officer Erlan ({phone}) called about a loan attempt from "
         "Shymkent and asked me to move money to reserve card {card} for protection. Loss: {amount}."),
    ],
    # B: phone pool, safe account
    "SAFE_ACCOUNT": [
        ("Со мной связалась «специалист Национального банка» Динара с номера {phone}. Сказала, что мои "
         "сбережения под угрозой и их надо перевести на защищённый депозитный счёт {iban}. Я отправила {amount}.",
         "'National Bank specialist' Dinara contacted me from {phone}. She said my savings were at risk and "
         "had to be moved to a protected deposit account {iban}. I sent {amount}."),
        ("Звонили с {phone}, женщина по имени Динара, «Нацбанк». Убедила, что нужно перевести всё на "
         "защищённый депозитный счёт {iban}, иначе деньги спишут. Перевёл {amount}.",
         "A woman named Dinara, 'National Bank', called from {phone} and convinced me to move everything to "
         "protected deposit account {iban} or lose it. I sent {amount}."),
    ],
    # C: phishing domain, loan status SMS
    "LOAN_STATUS_SMS": [
        ("Пришло SMS: «Статус вашего займа обновлён, проверьте детали: {url}». Перешла по ссылке, ввела "
         "данные карты и код из SMS. С карты списали {amount}.",
         "I got an SMS: 'Your loan status was updated, check details: {url}'. I opened the link, entered my "
         "card details and the SMS code. {amount} was taken from my card."),
        ("SMS про обновление статуса займа со ссылкой {url}. На сайте попросили подтвердить личность — "
         "ввёл номер карты и код. Потерял {amount}.",
         "An SMS about a loan status update with a link {url}. The site asked me to confirm my identity; I "
         "entered my card number and code. I lost {amount}."),
    ],
    # D: forwarding chain, police threat
    "POLICE_THREAT": [
        ("Позвонил «следователь Нурлан» с номера {phone}, сказал, что на моё имя оформлен кредит для "
         "финансирования преступной деятельности, и мне грозит уголовное дело. Чтобы «снять подозрения», "
         "велел перевести {amount} на карту {card}.",
         "'Investigator Nurlan' called from {phone}, said a loan in my name was funding crime and I faced a "
         "criminal case. To 'clear suspicion' he told me to transfer {amount} to card {card}."),
        ("Следователь (назвался Нурланом, {phone}) угрожал уголовным делом из-за кредита на моё имя. "
         "Я перевела {amount} на карту {card}, как он сказал.",
         "An investigator (called himself Nurlan, {phone}) threatened a criminal case over a loan in my "
         "name. I transferred {amount} to card {card} as instructed."),
    ],
    # E: script-only, investment
    "INVESTMENT": [
        ("В Telegram написал куратор Алия с платформы «KazOil Invest»: гарантированный доход 30 % в месяц от "
         "акций нефтяной компании. Первый взнос через карту {card}, потом попросили налог за вывод. "
         "Всего отдал {amount}. Её номер {phone}.",
         "Curator Aliya from the 'KazOil Invest' platform wrote on Telegram: guaranteed 30% monthly return on "
         "oil company shares. First deposit via card {card}, then a 'withdrawal tax'. I lost {amount} in total. "
         "Her number: {phone}."),
        ("Куратор Алия, платформа «KazOil Invest», обещала 30 % в месяц на акциях нефтяной компании. "
         "Вносил через карту {card}, за вывод потребовали налог. Потерял {amount}. Номер куратора {phone}.",
         "Curator Aliya, 'KazOil Invest' platform, promised 30% a month on oil company shares. I paid via card "
         "{card}; withdrawing required a 'tax'. Lost {amount}. Curator's number {phone}."),
    ],
    # F: two shared mules, marketplace prepayment
    "MARKETPLACE_PREPAY": [
        ("Покупала диван на маркетплейсе, продавец Санжар ({phone}) попросил предоплату 50 % на карту "
         "{card}, сказал, что отправит курьером СДЭК. Перевела {amount}, продавец пропал.",
         "I was buying a sofa on a marketplace; seller Sanzhar ({phone}) asked for 50% prepayment to card "
         "{card} and promised courier delivery. I sent {amount}; the seller vanished."),
        ("Продавец мебели Санжар ({phone}) с маркетплейса взял предоплату 50 % на карту {card} за доставку "
         "курьером. Отправил {amount}, больше на связь не выходит.",
         "Furniture seller Sanzhar ({phone}) from a marketplace took 50% prepayment to card {card} for courier "
         "delivery. I sent {amount}; no reply since."),
    ],
    # G: ATM drop recruitment
    "ATM_DROP_HELP": [
        ("Возле банкомата подошёл молодой человек, попросил помочь перевести деньги «брату» на карту {card}, "
         "обещал 5 000 тенге за помощь. Потом мою карту заблокировали, оказалось, через неё прошло {amount} "
         "от мошенников.",
         "A young man at an ATM asked me to help send money to his 'brother' on card {card}, promising 5,000 "
         "tenge. Later my card was blocked: {amount} of fraud money had gone through it."),
        ("У банкомата незнакомец попросил перевести наличные «брату» на карту {card} за 5 000 тенге. "
         "Теперь мою карту заблокировали из-за {amount} мошеннических денег.",
         "At an ATM a stranger asked me to send cash to his 'brother' on card {card} for 5,000 tenge. Now my "
         "card is blocked over {amount} of fraud money."),
    ],
}

# Second script-only campaign used by the hard variant.
HARD_EXTRA_SCRIPT: list[Template] = [
    ("Нашла объявление о работе «оценщик отзывов» на маркетплейсе, менеджер Камила дала задания, а потом "
     "попросила «выкупить заказ» через карту {card} для получения процента. Потеряла {amount}. Её номер {phone}.",
     "I found a 'review rater' job; manager Kamila gave tasks, then asked me to 'buy out an order' via card "
     "{card} to earn a percentage. I lost {amount}. Her number {phone}."),
    ("Работа «оценщик отзывов»: менеджер Камила попросила выкупить заказ через карту {card}, чтобы получить "
     "процент. Ушло {amount}. Номер Камилы {phone}.",
     "'Review rater' job: manager Kamila asked me to buy out an order via card {card} to get a percentage. "
     "{amount} gone. Kamila's number {phone}."),
]

GENERIC: dict[str, list[Template]] = {
    "BANK_SECURITY": [
        ("Звонили с {phone}, сказали, что с моей карты пытаются снять деньги, попросили код из SMS. "
         "Списали {amount}.",
         "A caller from {phone} said someone was trying to take money from my card and asked for the SMS "
         "code. {amount} was taken."),
        ("Сотрудник «службы безопасности» позвонил с {phone} и попросил назвать данные карты. Потеряла {amount}.",
         "A 'security service' employee called from {phone} and asked for my card details. I lost {amount}."),
    ],
    "SAFE_ACCOUNT": [
        ("Мне сказали по телефону {phone}, что счёт взломан, и попросили перевести деньги на безопасный счёт "
         "{iban}. Перевёл {amount}.",
         "On the phone ({phone}) I was told my account was hacked and asked to move money to a safe account "
         "{iban}. I sent {amount}."),
    ],
    "LOAN_STATUS_SMS": [
        ("Получил сообщение о займе со ссылкой {url}, ввёл данные — списали {amount}.",
         "I received a message about a loan with a link {url}, entered my details and lost {amount}."),
    ],
    "MARKETPLACE_PREPAY": [
        ("Хотела купить телефон по объявлению, продавец попросил перевести {amount} на карту {card}. "
         "Товар не пришёл. В объявлении был номер {phone}.",
         "I wanted to buy a phone from an ad; the seller asked me to send {amount} to card {card}. Nothing "
         "arrived. The ad listed {phone}."),
        ("Заказал шины через объявление, перевёл предоплату {amount} на карту {card}, продавец заблокировал меня.",
         "I ordered tyres from an ad, paid {amount} prepayment to card {card}; the seller blocked me."),
    ],
    "POLICE_THREAT": [
        ("Позвонили с {phone} якобы из полиции, угрожали делом и требовали {amount}. Я перевёл на карту {card}.",
         "Someone from {phone} claiming to be police threatened a case and demanded {amount}. I sent it to "
         "card {card}."),
    ],
    "INVESTMENT": [
        ("Вложил {amount} в криптобиржу по совету знакомого из Instagram, вывести деньги не могу. "
         "Платил на карту {card}.",
         "I put {amount} into a crypto exchange recommended by an Instagram contact and cannot withdraw. I paid "
         "to card {card}."),
    ],
    "ATM_DROP_HELP": [
        ("Незнакомый человек у банкомата попросил перевести деньги на карту {card}, я отказалась, но он "
         "успел снять {amount} с моей карты, пока я отвлеклась.",
         "A stranger at an ATM asked me to send money to card {card}; I refused but he took {amount} from my "
         "card while I was distracted."),
    ],
}

# Mentions of the legitimate marketplace support line (a hub, not a fraudster).
HUB_SENTENCES: list[Template] = [
    (" Сначала я звонила в поддержку маркетплейса по номеру {hub}, там сказали обратиться в полицию.",
     " I first called the marketplace support line {hub}; they told me to go to the police."),
    (" Поддержка ({hub}) ничем не помогла.",
     " Support ({hub}) could not help."),
    (" Я уточнял в справочной {hub}, но было поздно.",
     " I checked with the help line {hub}, but it was too late."),
]

# Complaints with no extractable identifiers at all.
VAGUE: list[Template] = [
    ("Мне позвонили и долго уговаривали, номер не запомнила, я перевела {amount} через терминал наличными.",
     "Someone called and pressured me for a long time; I don't remember the number. I paid {amount} in cash "
     "via a terminal."),
    ("В мессенджере написал «друг» с просьбой занять {amount}, оказалось, его аккаунт взломали.",
     "A 'friend' on a messenger asked to borrow {amount}; his account had been hacked."),
]

CHANNEL = {
    "BANK_SECURITY": "call", "SAFE_ACCOUNT": "call", "LOAN_STATUS_SMS": "sms",
    "MARKETPLACE_PREPAY": "marketplace", "POLICE_THREAT": "call", "INVESTMENT": "messenger",
    "ATM_DROP_HELP": "in_person",
}

TYPOS = {"перевела": "перевила", "карту": "карут", "номер": "номр", "деньги": "денги", "банка": "банко"}
