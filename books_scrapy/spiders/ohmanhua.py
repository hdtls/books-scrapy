import base64
import demjson
import scrapy

from books_scrapy.items import Manga
from books_scrapy.items import MangaChapter
from books_scrapy.items import Image
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from scrapy import Request


class OHManhuaSpider(scrapy.Spider):
    name = "ohmanhua"
    base_url = "https://www.cocomanhua.com"
    start_urls = ["https://www.cocomanhua.com/15177"]

    def start_requests(self):
        for url in self.start_urls:
            yield Request(url, self.parse)

    def parse(self, response):
        self.__parse_detail_page(response)

    def __parse_detail_page(self, html):
        manga = Manga()
        manga["name"] = html.css("dd.fed-deta-content h1::text").get()

        cover_image = Image()
        cover_image["name"] = "cover.jpg"
        cover_image["url"] = html.css(
            "dt.fed-deta-images a::attr(data-original)"
        ).get()

        cover_image["file_path"] = self.__get_img_store() + "/" + manga["name"]

        manga["cover_image"] = cover_image

        li_list = html.css("dd.fed-deta-content ul li")
        for li in li_list:
            label = li.css("span::text").get()
            if label == "状态":
                manga["status"] = li.css("a::text").get()
            elif label == "作者":
                fmt_author_label = li.css("a::text").get()
                if " " in fmt_author_label:
                    manga["authors"] = fmt_author_label.split(" ")
                elif "x" in fmt_author_label:
                    manga["authors"] = fmt_author_label.split("x")
                elif:
                    manga["authors"] = [fmt_author_label]
            elif label == "类别":
                manga["categories"] = li.css("a::text").getall()
            elif label == "简介":
                manga["excerpt"] = li.css("div::text").get()

        chap_path_list = html.css("div.all_data_list li a::attr(href)").getall()

        # for path in chap_path_list:
            # url = self.base_url + path
            # yield Request(url, self.__parse_chapter_page, meta=manga)

    def __get_img_store(self):
        return "/".join([self.settings["IMAGES_STORE"], self.name])

    def __parse_chapter_page(self, html):
        chapter_data = response.css('script:contains("var C_DATA")::text').get()[12:-2]

        if chapter_data is None:
            return None

        chapter_data = self.__decode(chapter_data)

        if chapter_data is None:
            return None

        chapter = MangaChapter()

        img_dir_path = "/".join(
            [
                self.settings["IMAGES_STORE"],
                self.name,
                chapter_data["mhname"],
                chapter_data["pagename"],
            ]
        )
        chapter["image_urls"] = self.__get_img_list(chapter_data, img_dir_path)

        return chapter

    def __get_img_list(self, chap, img_dir_path):
        total_img_size = int(chap["total_img_size"])
        image_list = []

        if total_img_size is None:
            return image_list

        base_url = "https://" + chap["domain"] + "/comic/" + chap["img_path"]

        start_index = int(chap["startimg"])

        # Make start index to zero
        if start_index != 0:
            start_index = 0

        for img_index in range(total_img_size):
            start_index += 1

            image = Image()
            image["name"] = chap["pagename"]
            image["url"] = base_url + str(start_index).zfill(4) + ".jpg"
            image["file_path"] = img_dir_path + "/" + str(img_index).zfill(4) + ".jpg"
            image_list.append(image)

        return image_list

    def __decode(self, ciphertext):
        assert isinstance(ciphertext, str)

        plaintext = self.__try_decrypt(ciphertext)

        mh_key = "mh_info="
        img_key = "image_info="

        mh_info = None
        image_info = None

        """
        mh_info = {
            startimg:1,
            enc_code1:"cmtuSTY3NmtpREpnbnhsVXk5aFV0Zz09",
            mhid:"15177",
            enc_code2:"dExESkN1a05ZcU9wTVRobEVMY2V5aWdVRU9xZllhOFN3SEZhRXZVRTBPWFdwbTJyRFhVMWZISDZXSnRBVExsSmthejhEeUZVSnV5QVNGeTRmdEY0UlpobkwyWWx4ank3c0tCZ3ZDUk05c1k9",
            mhname:"大王饶命",
            pageid:3254380,
            pagename:"205 跳级生吕小鱼",
            pageurl:"1/209.html",
            readmode:3,
            maxpreload:5,
            defaultminline:1,
            domain:"img.cocomanhua.com",
            manga_size:"",
            default_price:0,
            price:0
        };
        image_info = {
            img_type:"",
            urls__direct:"",
            line_id:1,
            local_watch_url:""
        }
        """
        for obj in plaintext.split(";"):
            if mh_info is None and mh_key in obj:
                va_list = obj.split(mh_key)
                mh_info = demjson.decode(va_list[1])

            if image_info is None and img_key in obj:
                va_list = obj.split(img_key)
                image_info = demjson.decode(va_list[1])

        if mh_info["enc_code1"]:
            mh_info["total_img_size"] = self.__try_decrypt(mh_info["enc_code1"])

        if mh_info["enc_code2"]:
            mh_info["img_path"] = self.__try_decrypt(
                mh_info["enc_code2"],
                "fw125gjdi9ertyui",
            )

        return mh_info

    def __try_decrypt(self, ciphertext, key=None, default_key=None):
        ciphertext = base64.b64decode(ciphertext)

        # 2019/9/27: "JRUIFMVJDIWE569j"
        # 2020/8/21 14:39:33: "fw12558899ertyui"
        # 2021/1/8: var __READKEY = 'fw122587mkertyui';
        key_list = ["fw122587mkertyui", "fw12558899ertyui", "JRUIFMVJDIWE569j"]

        if isinstance(default_key, str):
            key_list.insert(0, default_key)

        if isinstance(key, str):
            key_list.insert(0, key)

        for k in key_list:
            plaintext = self.__decrypt(ciphertext, k)

            if plaintext is not None:
                return plaintext

        return ciphertext

    def __decrypt(self, ciphertext, key):
        if isinstance(key, str):
            key = key.encode("utf-8")

        ciphertext = base64.b64decode(ciphertext)

        if isinstance(ciphertext, str):
            ciphertext = ciphertext.encode("utf-8")

        decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()

        plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        plaintext = self.__pkcs7_unpadding(plaintext)

        # Convert bytes to utf8 string.
        return plaintext.decode()

    def __pkcs7_unpadding(self, data):
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        return unpadder.update(data) + unpadder.finalize()