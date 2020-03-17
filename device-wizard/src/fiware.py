import json
import logging

import hashlib
import requests

logging.basicConfig(level=logging.DEBUG)


class BaseRequest(object):
    # def get(self, url, data, headers):
    #     e = None
    #     result = {}
    #     try:
    #         r = requests.get(url, headers=headers, timeout=60)
    #         result = r.json()
    #         r.raise_for_status()
    #     except requests.exceptions.RequestException as err:
    #         e = err
    #         logging.error("Error", err)
    #     if e is None:
    #         return {'status': True, "result": result}
    #     else:
    #         return {'status': False, 'error': e}

    def post(self, url, data, headers):
        e = None
        try:
            r = requests.post(url, data=data, headers=headers, timeout=60)
            r.raise_for_status()
        except requests.exceptions.RequestException as err:
            e = err
            logging.error("Error", err)
        if e is None:
            return {'status': True}
        else:
            return {'status': False, 'error': e}


class Orion(BaseRequest):
    """Class wrapper for Fiware Orion service"""
    url = 'http://orion:1026'
    header = {''}
    headers = {'Content-type': 'application/ld+json'}
    headers_with_link = {
        'Content-type': 'application/ld+json',
        'Link': '<http://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'}

    def __init__(self, config=''):
        try:
            self.url = config['orion']
        except Exception as e:
            logging.error('Init orion', e)

    def create_entity(self, data):
        """Create entity via REST API call to FIWARE Orion instance"""
        url = '{}/ngsi-ld/v1/entities'.format(self.url)
        return self.post(url, data=data, headers=self.headers)

    def update_entity(self, device_id, data):
        """Create entity via REST API call to FIWARE Orion instance"""
        url = '{}/ngsi-ld/v1/entities/{}/attrs'.format(self.url, device_id)
        return self.post(url, data=data, headers=self.headers)

    def get_entities(self, type, offset=0, limit=20):
        """Get list of entities from FIWARE Orion instance"""
        # url = '{}/ngsi-ld/v1/entities?type={}&offset={}&limit={}'.format(self.url, type, offset, limit)
        url = '{}/ngsi-ld/v1/entities?type={}'.format(self.url, type, offset, limit)
        r = requests.get(url, headers=self.headers_with_link)
        return r.json()

    def get_entity_by_id(self, id):
        """Get entity from FIWARE Orion instance"""
        # url = '{}/ngsi-ld/v1/entities?type={}&offset={}&limit={}'.format(self.url, type, offset, limit)
        url = '{}/ngsi-ld/v1/entities/{}'.format(self.url, id)
        r = requests.get(url, headers=self.headers)
        return r.json()

    def delete_entity(self, device_id):
        """Remove device from the orion"""
        url = '{}/ngsi-ld/v1/entities/{}'.format(self.url, device_id)
        r = requests.delete(url, headers=self.headers)
        return r

    def get_version(self):
        """Return version of Orion"""
        url = '{}/version'.format(self.url)
        try:
            r = requests.get(url)
            if r.status_code == 200:
                return r.json()['orionld version']
        except Exception as e:
            pass
        return ''


class IoTAgent(BaseRequest):
    """Class wrapper for Fiware IoT Agent service"""
    url = 'http://iot-agent:4041'
    headers = {'Content-type': 'application/json', 'fiware-service': 'openiot', 'fiware-servicepath': '/'}

    def __init__(self, config=''):
        try:
            self.url = config['iotagent']
            self.orion = config['orion']
        except Exception as e:
            logging.error('Init iotgent', e)

    def _hash(self, type):
        m = hashlib.md5()
        m.update(type)
        return m.hexdigest()

    def create_service(self, api_key, device_type):
        url = '{}/iot/services'.format(self.url)
        data = {'services': [
            {
                'apikey': api_key,
                'cbroker': self.orion,
                'entity_type': str(self._hash(device_type)),
                "resource": '/iot/{device_type}'.format(device_type=device_type)
            }
        ]}
        return self.post(url, data=json.dumps(data), headers=self.headers)

    def create_device(self, device_dict):
        """Create entity via REST API call to FIWARE IoT Agent instance"""
        devices = {'devices': [device_dict]}
        url = '{}/iot/devices'.format(self.url)
        return self.post(url, data=json.dumps(devices), headers=self.headers)

    def get_entities(self, offset=0, limit=20):
        """Get list of entities from FIWARE IoT Agent instance"""
        url = '{}/iot/devices'.format(self.url, offset, limit)
        r = requests.get(url, headers=self.headers)
        return r.json()

    def get_entity_by_id(self, id):
        """Get entity from FIWARE IoTAgent instance"""
        url = '{}/iot/devices/{}'.format(self.url, id)
        r = requests.get(url, headers=self.headers)
        return r.json()

    def delete_entity(self, device_id):
        """Remove device from the IoT Agent"""
        url = '{}/iot/devices/{}'.format(self.url, device_id)
        r = requests.delete(url, headers=self.headers)
        return r

    def get_version(self):
        """Return version of IoT Agent"""
        url = '{}/version'.format(self.url)
        try:
            r = requests.get(url)
            if r.status_code == 200:
                return r.json()['version']
        except Exception as e:
            pass
        return ''
