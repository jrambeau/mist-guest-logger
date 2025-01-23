import os
import time
import json
import requests
import websocket
import sys
import re
import logging
import signal
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from apivariables import mist_url, token, org_id

# Déterminer le répertoire du script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Configurer le logging
def setup_logging():
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Configurer le fichier de log avec rotation
    log_file = os.path.join(script_dir, 'application.log')
    file_handler = RotatingFileHandler(log_file, maxBytes=1024*1024*5, backupCount=5)  # 5 Mo par fichier, garder 5 backups
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)  # Ajuster le niveau de log selon les besoins

    # Configurer le logging vers la console (optionnel)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)  # Ajuster le niveau de log selon les besoins

    # Obtenir le logger racine et définir les handlers
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

# Initialiser la configuration du logging
setup_logging()


def datetime_converter(o):
    if isinstance(o, datetime):
        return o.isoformat()

# Fonction pour récupérer les sites de l'organisation
def fetch_sites():
    sites_url = f"{mist_url}orgs/{org_id}/sites"
    headers = {'Content-Type': 'application/json', 'Authorization': f"Token {token}"}
    retry_strategy = {'max_retries': 5, 'backoff_time': 1}

    for attempt in range(retry_strategy['max_retries']):
        try:
            response = requests.get(sites_url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", retry_strategy['backoff_time']))
                logging.warning(f"Request throttled. Retrying in {retry_after} seconds...")
                time.sleep(retry_after)
                retry_strategy['backoff_time'] *= 2  # Backoff exponentiel
            else:
                logging.error(f"HTTP Error: {e}")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {e}")
        time.sleep(retry_strategy['backoff_time'])

    logging.error("Max retries exceeded. Exiting.")
    return []

def sanitize_filename(filename):
    return re.sub(r'[\/:*?"<>|]', '_', filename)

# Fonction pour traiter les messages reçus via WebSocket
def process_message(ws, message):
    # Vérifier la présence de la clé 'data' et son type
    #logging.info(f"Réception d'un message du WebSocket pour le site {ws.current_siteid}")
    if 'data' not in message or not isinstance(message['data'], str):
        return

    try:
        message['data'] = json.loads(message['data'])

        # On vérifie si le User est un guest ou non
        if (message.get('data', {}).get('is_guest')) or ('guest' in message['data'].get('ssid', '').lower()) or ('invite' in message['data'].get('ssid', '').lower()) or ('hotspot' in message['data'].get('ssid', '').lower()):
            
            logging.info(f"User {message['data']['mac']} EST un guest")

            # On vérifie s'il s'agit d'un nouveau Guest ou s'il a déjà été traité par le script
            guest_identifier = {'mac': message['data']['mac'], 'ip': message['data']['ip']}
            guest_existe = any(element == guest_identifier for element in ws.guest_list)
            if guest_existe == False:
                logging.info(f"Nouvel invité détecté: {message['data']['mac']} {message['data']['ip']} sur le site {ws.current_siteid} {next((item['name'] for item in ws.sites if item['id'] == ws.current_siteid), None)}")
                # Une requête Get est nécessaire sur l'adresse MAC du client car la balise [guest] n'est pas présente dans la réponse du Websocket
                headers = {'Content-Type': 'application/json', 'Authorization': f"Token {token}"}
                clientstat_url = '{0}sites/{1}/stats/clients/{2}'.format(mist_url,ws.current_siteid,message['data']['mac'])
                logging.info(f"Envoi d'une requête GET pour obtenir les infos supplémentaires du guest {message['data']['mac']}")
                response_clientstat = requests.get(clientstat_url, headers=headers) #Pour la liste des clients actuellement connectés et leur statistiques (dont l'adresse IP)
                logging.info(f"Code retour de la requête GET : {response_clientstat.status_code}")
                if response_clientstat.status_code == 200:
                    # Parse de la réponse
                    clientstat = json.loads(response_clientstat.content.decode('utf-8'))
                    # Appel de la fonction handle_guest_data pour récupérer les informations supplémentaires du guest
                    logging.info(f"Requête GET OK, go pour gestion des données pour ce guest")
                    handle_guest_data(ws, clientstat, guest_identifier)
                else:
                    # Erreur dans la requête GET. Le guest sera traité dans une prochaine itération.
                    logging.info(f"Erreur de gestion des données pour ce guest en raison de l'échec de la requête GET. Le guest sera traité lors du prochain message envoyé par le Websocket")
            else:
                logging.info(f"Guest déjà enregistré dans les logs")
        else:
            logging.info(f"User {message['data']['mac']} n'est pas un guest")
    except json.JSONDecodeError as e:
        logging.error(f"Décodage JSON échoué: {e}")
    except KeyError as e:
        logging.error(f"Clé attendue manquante: {e}")
    except Exception as e:
        logging.error(f"Erreur non gérée lors du traitement du message: {e}")


# Fonction pour gérer les données des invités
def handle_guest_data(ws, clientstat, guest_identifier):
    logging.info(f"Fonction handle_guest_data : extraction des informations pour le nouveau guest {clientstat['mac']}")

    # Extraire les données de l'invité
    guest_data = {
        'mac': clientstat["mac"],
        'ip': clientstat["ip"],
        'assoc_time': datetime.fromtimestamp(clientstat["assoc_time"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        'ssid': clientstat['ssid'],
        'site_id': ws.current_siteid,
        'site_name': next((item['name'] for item in ws.sites if item['id'] == ws.current_siteid), None),
        'event_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
    }

    # Extraire les données additionnelles dans le dictionnaire [guest] s'il est présent
    if 'guest' in clientstat:
        logging.info(f"Balise [guest] présente !")
        guest_data["guest_data_present"] = True
        if 'authorized_time' in clientstat["guest"]: guest_data['authorized_time'] = datetime.fromtimestamp(clientstat["guest"]["authorized_time"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        if 'auth_method' in clientstat['guest']: guest_data['auth_method'] = clientstat["guest"]["auth_method"]
        if 'access_code_email' in clientstat['guest']: guest_data['access_code_email'] = clientstat["guest"]["access_code_email"]
        if 'name' in clientstat['guest']: guest_data["name"] = clientstat['guest']['name']
        if 'email' in clientstat['guest']: guest_data['email'] = clientstat["guest"]["email"]
        if 'company' in clientstat['guest']: guest_data['company'] = clientstat["guest"]["company"]
        if 'sponsor_name' in clientstat['guest']: guest_data['sponsor_name'] = clientstat["guest"]["sponsor_name"]
        if 'sponsor_email' in clientstat['guest']: guest_data['sponsor_email'] = clientstat["guest"]["sponsor_email"]
    else:
        logging.info(f"Pas de balise [guest] détaillé pour cet invité")

    # Ajouter les données de l'invité à un fichier JSON unique
    try:
        filename = os.path.join(script_dir, "mist-guests-logger-logs-"+datetime.now().strftime('%Y-%m-%d')+".json")
        with open(filename, "a+") as file:
            json.dump(guest_data, file, indent=4)  # Écrire les données mises à jour dans le fichier
        logging.info(f"Données de l'invité {guest_data['mac']} ajoutées à {filename}.")
    except IOError as e:
        logging.error(f"Échec de l'écriture des données de l'invité dans le fichier: {e}")
    except Exception as e:
        logging.error(f"Une erreur s'est produite lors de la sauvegarde des données de l'invité: {e}")

    ws.guest_list.append(guest_identifier) # Ajout du guest dans la liste des guests logués



# Fonction de rappel pour les messages WebSocket
def on_message(ws, message):
    try:
        message = json.loads(message)  # Assurer que le message est un dictionnaire
        
        # Extraire le site-id
        match = re.search(r'/sites/([^/]+)/stats', message['channel'])
        ws.current_siteid = match.group(1)
        
        process_message(ws, message)
    except json.JSONDecodeError as e:
        logging.error(f"Décodage JSON échoué: {e}")
    except Exception as e:
        logging.error(f"Erreur lors du traitement du message pour le site {ws.current_siteid}: {e}")

# Fonction de rappel pour les erreurs WebSocket
def on_error(ws, error):
    logging.error(f"Erreur Websocket : {error}")

# Fonction de rappel pour la fermeture du WebSocket
def on_close(ws, close_status_code, close_msg):
    logging.info(f"Websocket fermé avec le code et message: code {close_status_code}, message: {close_msg}")
    time.sleep(5)

# Fonction de rappel pour l'ouverture du WebSocket
def on_open(ws):
    for site in ws.sites:
        logging.info(f"Souscription au topic /sites/{site['id']}/stats/clients (site {site['name']})...")
        ep = f'/sites/{site["id"]}/stats/clients'
        ws.send(json.dumps({'subscribe': ep}))

# Gestionnaire de signal pour l'interruption clavier (Ctrl+C)
def signal_handler(sig, frame):
    logging.info(f"INTERRUPTION CLAVIER capturée, fermeture et reconnexion WebSocket dans 5 secondes... Pour fermer le programme complètement, terminer le processus.")
    ws.close()

# Fonction principale
if __name__ == "__main__":

    #websocket.enableTrace(True)    # For Websocket debugging
    signal.signal(signal.SIGINT, signal_handler)        # Pour capturer les interruptions clavier

    guest_list = list()  # Pour le suivi des invités uniques

    logging.info('Lancement du programme. Surveillance des sessions des utilisateurs invités...')
    sites = fetch_sites()

    if not sites:
        logging.info("Aucun site à surveiller. Sortie.")
    else:
        for site in sites:
            site['name'] = site['name'].replace(" ", "_")  # Remplacer les espaces par des underscores dans le nom du site
        
        start_time = time.time()
        c = 1
        ws = None
        
        try:
            while True:
                if not ws or not ws.sock or not ws.sock.connected:
                    header = [f'Authorization: Token {token}']
                    ws_url = 'wss://api-ws.eu.mist.com/api-ws/v1/stream'
                    ws = websocket.WebSocketApp(ws_url, header=header,
                                                on_open=lambda ws: on_open(ws),
                                                on_message=lambda ws, msg: on_message(ws, msg),
                                                on_error=on_error,
                                                on_close=on_close)
                    ws.sites = sites
                    ws.guest_list = guest_list
                    ws.run_forever()

                logging.info(f"reconnect [%s]" % c)
                time.sleep(5)
                c += 1

        except Exception as e:
            logging.error(f"Erreur dans fonction principale: {e}")
            ws.close()