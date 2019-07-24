from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException

from os import getcwd
from platform import system
from functools import total_ordering
import csv

AMEX_LOGIN = ""
AMEX_PW = ""
NOTIFICATION_THRESHOLD = 10  # The number of offers to process/write before printing an update


@total_ordering
class Offer:
    def __init__(self, text, merchant, expiration):
        self.text = text
        self.merchant = merchant
        self.expiration = expiration
        # Represents each cards' enrollment state
        self.enrolled_cards = []

    def __eq__(self, other):
        if isinstance(other, Offer):
            return self.text == other.text and self.merchant == other.merchant and self.expiration == other.expiration
        return False

    def __hash__(self):
        return hash((self.text, self.merchant, self.expiration))

    def __repr__(self):
        return f"{self.text} at {self.merchant} expiring on {self.expiration}"

    def __lt__(self, other):
        return self.merchant < other.merchant

    def get_csv_line(self):
        return [self.text, self.merchant, self.expiration] + [card.upper() for card in self.enrolled_cards]


def get_driver():
    operating_system = system()
    if operating_system == "Darwin":
        filename = "chromedriver.mac"
    elif operating_system == "Linux":
        filename = "chromedriver.linux"
    else:  # Windows
        filename = "chromedriver.windows"
    driver_path = f"{getcwd()}/{filename}"

    options = Options()
    options.add_argument("--headless")
    options.add_argument('window-size=1920x1080')  # The website layout changes for the default window size
    options.add_argument("--start-maximized")
    return webdriver.Chrome(executable_path=driver_path, options=options)


def open_card_stack(driver, initial_open=False):
    card_stack_css = "section.axp-account-switcher span.card-stack button"
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, card_stack_css))
        )
    except NoSuchElementException:
        print(f"Ran into error waiting for the card stack to load. Is your username/pw correct?")
        return

    card_stack = driver.find_element_by_css_selector(card_stack_css)

    try:
        card_stack.click()
    except ElementClickInterceptedException:
        print("Something unexpected went wrong with opening the card stack. Try running the script again")
        return

    if initial_open:
        view_all = driver.find_element_by_css_selector('[title="View All"]')
        view_all.click()


# Assumes card stack is open
def get_card_names_from_account_list(driver, num_cards):
    account_names = []
    # XPath starts at 1
    for i in range(1, num_cards + 1):
        account_name = driver.find_element_by_xpath(f'//*[@id="accounts"]/section[{i}]/header/section/div/div[2]/div/p')
        account_names.append(account_name.text)
    return account_names


def process_card(driver, offer_map, account_list, card_idx):
    # Select the card to process
    account_list[card_idx].click()
    offers_xpath = '//*[@id="offers"]/div/section[2]/section/div'
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, offers_xpath))
        )
    except Exception as e:
        print(f"Ran into error waiting for the offers section to load: {e}")
        return

    # Process eligible offers
    add_card_to_offers(driver, offer_map, account_list, card_idx, offers_xpath, "Available")
    driver.find_element_by_xpath('//*[@id="offers-nav"]/div[1]/div/a[2]').click()  # Click on enrolled offers
    add_card_to_offers(driver, offer_map, account_list, card_idx, offers_xpath, "Enrolled")
    driver.find_element_by_xpath('//*[@id="offers-nav"]/div[1]/div/a[1]').click()  # Click on available offers


# Selects the card, opens all the offers, peruses
def add_card_to_offers(driver, offer_map, account_list, card_idx, offers_xpath, status):

    all_offers = driver.find_elements_by_xpath(offers_xpath)
    i = 1
    for offer_body in all_offers:
        try:
            offer_info = offer_body.find_element_by_class_name("offer-info")
        except NoSuchElementException:
            # No enrolled or available offers
            return

        if "Spend" not in offer_info.text:  # Ignore Amex's random ads
            continue

        offer_info_children = offer_info.find_elements_by_css_selector("p")
        offer = offer_info_children[0].text
        merchant = offer_info_children[1].text
        expiration = offer_body.find_element_by_css_selector(".offer-expires span span").text

        offer_hash = hash((offer, merchant, expiration))
        offer_obj = offer_map.get(offer_hash, Offer(offer, merchant, expiration))

        # Initialize the list determining whether each particular card is enrolled in this offer
        if len(offer_obj.enrolled_cards) == 0:
            offer_obj.enrolled_cards = ["N/A"] * len(account_list)

        offer_obj.enrolled_cards[card_idx] = status
        offer_map[offer_hash] = offer_obj
        if i % NOTIFICATION_THRESHOLD == 0:
            print(f"Processed {i} {status} offers")
        i += 1


def write_offers_to_file(offer_objects, card_names):
    print("Started writing offers to file")
    headers = ["Offer", "Merchant", "Expiration"] + card_names
    i = 1
    with open('offers.csv', 'w') as csvfile:
        writer = csv.writer(csvfile, delimiter=',', newline='')
        writer.writerow(headers)
        for offer_obj in offer_objects:
            writer.writerow(offer_obj.get_csv_line())
            if i % NOTIFICATION_THRESHOLD == 0:
                print(f"Wrote offer {i} of {len(offer_objects)}")
            i += 1

    print("Finished writing all offers!")


def login(driver):
    print("Logging in")
    # Wait for the login fields and button to load
    try:
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "login-user"))
        )
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "login-password"))
        )
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "login-submit"))
        )
    except Exception as e:
        print(f"Ran into error waiting for the login form to load: {e}")
        return
    username_field = driver.find_element_by_id("login-user")
    username_field.send_keys(AMEX_LOGIN)

    password_field = driver.find_element_by_id("login-password")
    password_field.send_keys(AMEX_PW)

    login_button = driver.find_element_by_id("login-submit")
    login_button.click()
    print("Finished logging in")


def main():
    if AMEX_LOGIN == "" or AMEX_PW == "":
        print("Fill out your username and/or password")
        return

    driver = get_driver()
    driver.get("https://global.americanexpress.com/")

    login(driver)

    driver.get("https://global.americanexpress.com/offers/eligible/")

    open_card_stack(driver, initial_open=True)

    account_list = driver.find_elements_by_xpath('//*[@id="accounts"]/section')
    num_cards = len(account_list)
    card_names = get_card_names_from_account_list(driver, num_cards)

    offer_map = {}

    for i in range(num_cards):
        # Assume stack is open
        print(f"Processing offers for card: {card_names[i]}")

        # Regenerate account list elements as the references refresh after clicking on them
        account_list = driver.find_elements_by_xpath('//*[@id="accounts"]/section')

        process_card(driver, offer_map, account_list, i)
        print(f"Finished processing offers for card: {card_names[i]}")
        open_card_stack(driver)

    driver.close()
    print("Finished processing all offers")
    offer_list = list(offer_map.values())
    offer_list.sort()
    write_offers_to_file(offer_list, card_names)


if __name__ == "__main__":
    main()
