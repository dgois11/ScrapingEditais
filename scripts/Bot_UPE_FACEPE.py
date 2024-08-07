#!/usr/bin/env python
# coding: utf-8

# # **Bot para coleta dos editais**

# In[2]:


get_ipython().system('pip install webdriver_manager')
get_ipython().system('pip install unidecode')
import requests
import time
from bs4 import BeautifulSoup
import time
import os
import pickle
import requests
import re
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from unidecode import unidecode


# In[ ]:


class BotAPI:
    def __init__(self, base_url, username, senha):
        self.base_url = base_url
        self.username = username
        self.senha = senha
        self.session = requests.Session()

    def login(self):
        url = f"{self.base_url}/upe/usuario/login"
        payload = {
            "login": self.username,
            "senha": self.senha
        }
        headers = {
            "Content-Type": "application/json"
        }
        response = self.session.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            print("Login bem-sucedido!")
        else:
            print(f"Falha no login. Status code: {response.status_code}")
            print("Resposta:", response.text)
        return response.status_code == 200

    def criar_edital(self, nome, data_publicacao):
        url = f"{self.base_url}/upe/edital"
        payload = {
            "nome": nome,
            "dataPublicacao": data_publicacao,
            "idUsuario": 1,  # Usando ID de usuário 1
            "idOrgaoFomento": 1  # Fixo
        }
        headers = {
            "Content-Type": "application/json"
        }
        response = self.session.post(url, json=payload, headers=headers)
        if response.status_code == 201:
            print("Edital criado com sucesso!")
            print("Resposta:", response.json())
            return response.json()  # Assuming the response contains the created edital details
        else:
            print(f"Falha ao criar edital. Status code: {response.status_code}")
            print("Resposta:", response.text)
        return None

    def adicionar_pdf(self, id_edital, file_path):
        url = f"{self.base_url}/upe/edital/inserir/{id_edital}/pdf"
        files = {
            'edital_pdf': (os.path.basename(file_path), open(file_path, 'rb'), 'application/pdf')
        }
        response = self.session.post(url, files=files)
        if response.status_code == 200:
            print("PDF adicionado com sucesso!")
            print("Resposta:", response.json())
        else:
            print(f"Falha ao adicionar PDF. Status code: {response.status_code}")
            print("Resposta:", response.text)

def download_file(url, local_filename):
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_filename, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return local_filename

def extract_publication_date(parent_div):
    if parent_div:
        text = parent_div.get_text(separator=" ").strip()
        start = text.find('Publicação:')
        if start != -1:
            date_text = text[start + len('Publicação:'):].strip()
            return date_text
    return None

def convert_date_format(date_str):
    months = {
        'janeiro': '01',
        'fevereiro': '02',
        'março': '03',
        'abril': '04',
        'maio': '05',
        'junho': '06',
        'julho': '07',
        'agosto': '08',
        'setembro': '09',
        'outubro': '10',
        'novembro': '11',
        'dezembro': '12'
    }
    for pt_month, num_month in months.items():
        if pt_month in date_str:
            date_str = date_str.replace(pt_month, num_month)
            break
    date_str = date_str.replace(' de ', '/')
    try:
        date = datetime.strptime(date_str, "%d/%m/%Y")
        return date.strftime("%d/%m/%Y %H:%M:%S")
    except ValueError as e:
        print(f"Erro ao converter data: {e}")
        
        return None

def sanitize_folder_name(name):
    name = name.replace('/', '-')
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', ' ', name)
    name = name.strip()
    return name

def scrape_site(url, download_folder, bot_api):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        edital_conteudos = soup.find_all('div', class_='edital-conteudo')
        previous_folder = None

        for index, edital in enumerate(edital_conteudos):
            title_link = edital.find('a', href=True)
            if title_link and title_link['href'].endswith('.pdf'):
                post_title = title_link.get_text(strip=True)
                publication_date = extract_publication_date(edital)
                if publication_date:
                    formatted_date = convert_date_format(publication_date)
                    if formatted_date:
                        pdf_filename = title_link['href'].split('/')[-1]
                        pdf_name = os.path.splitext(pdf_filename)[0]  # Nome do edital sem a extensão .pdf
                        sanitized_title = sanitize_folder_name(pdf_name)  # Usando o nome do arquivo como nome do edital
                        sanitized_date = publication_date.replace('/', '-')
                        folder_name = f"{sanitized_title} - {sanitized_date}"

                        if previous_folder:
                            adendo_check = edital.find_previous_sibling('div', class_='edital-conteudo').find('span', style="font-size: 82%")
                            if adendo_check:
                                local_folder = os.path.join(previous_folder, folder_name)
                            else:
                                local_folder = os.path.join(download_folder, folder_name)
                                previous_folder = local_folder
                        else:
                            local_folder = os.path.join(download_folder, folder_name)
                            previous_folder = local_folder

                        pdf_filepath = download_file(title_link['href'], pdf_filename)
                        print(f"Downloaded {pdf_filepath}")

                        edital_data = bot_api.criar_edital(sanitized_title, formatted_date)
                        if edital_data:
                            bot_api.adicionar_pdf(edital_data['id'], pdf_filepath)
                            print(f"Successfully posted {pdf_filepath} to API")
                            os.remove(pdf_filepath)  # Remove the file after posting
                        else:
                            print(f"Failed to create edital for {pdf_filepath}")
                    else:
                        print(f"Failed to convert date for {post_title}")

                else:
                    print(f"Could not extract publication date for {post_title}")
                    print(f"Parent div content: {edital}")

            if index < len(edital_conteudos) - 1:
                next_edital = edital_conteudos[index + 1]
                adendo_span = next_edital.find('span', style="font-size: 82%")
                if adendo_span and previous_folder:
                    continue
                else:
                    previous_folder = None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")

def monitor_sites(folders, bot_api):
    while True:
        for url, folder_name, scraper_function in folders:
            scraper_function(url, folder_name, bot_api)
        time.sleep(60)

# Configurações do bot
base_url = "https://projetoeditaisback.onrender.com"
username = "bot"
senha = "12345678"

# Criando uma instância do bot
bot_api = BotAPI(base_url, username, senha)

# Realizando o login
if bot_api.login():
    site_scrapers = [
        ('https://www.facepe.br/editais/todos/?c=todos', 'facepe', scrape_site)
    ]

    monitor_sites(site_scrapers, bot_api)
else:
    print("Falha ao realizar login. Verifique as credenciais.")

