import json
import logging

import os
from flask import Flask, render_template, redirect, request, g
from flask_oidc import OpenIDConnect

from datamodel import Datamodel
from fiware import Orion, IoTAgent
from forms import TypesForm, FormService
from idm import IDM

logging.basicConfig(level=logging.DEBUG)


def create_app(device_wizard_config, client_secret):

    app = Flask(__name__, static_folder='../static', template_folder='../templates')

    app.config.update({
        'SECRET_KEY': 'SomethingNotEntirelySecret',
        'TESTING': True,
        'DEBUG': True,
        'OIDC_CLIENT_SECRETS': client_secret,
        'OIDC_ID_TOKEN_COOKIE_SECURE': False,
        'OIDC_REQUIRE_VERIFIED_EMAIL': False,
        'OIDC_USER_INFO_ENABLED': True,
        'OIDC_OPENID_REALM': 'n5geh',
        'OIDC_SCOPES': ['openid', 'email', 'profile'],
        'OIDC_INTROSPECTION_AUTH_METHOD': 'client_secret_post',
        'FIWARE': device_wizard_config['fiware'],
        'DEVICE_IDM': device_wizard_config['device_idm'],
        'DATAMODEL': device_wizard_config['datamodel'],
        'IDM': device_wizard_config['idm']
    })

    oidc = OpenIDConnect(app)  # OpenIDConnect provides security mechanism for API

    datamodel = Datamodel(config=app.config['DATAMODEL'])

    orion = Orion(config=app.config['FIWARE'])

    iotagent = IoTAgent(config=app.config['FIWARE'])

    idm = IDM(config=app.config['DEVICE_IDM'])

    formservice = FormService()

    @app.errorhandler(404)
    def not_found(e):
        """Render page in case wrong URL"""
        return render_template("404.html")

    @app.before_request
    def before_request():
        """Add user details to request"""
        if oidc.user_loggedin:
            info = oidc.user_getinfo(['preferred_username', 'email', 'sub', 'given_name', 'family_name'])
            g.user = info.get('preferred_username')
            g.fullname = '{} {}'.format(info.get('given_name'), info.get('family_name'))
            g.account_url = 'https://auth.n5geh.de/auth/realms/n5geh/account'
        else:
            g.user = None
            g.fullname = None

    @app.route('/')
    def index():
        """Default web page"""
        return redirect('/dashboard')

    @app.route('/dashboard')
    @oidc.require_login
    def dashboard():
        """Dashboard for managing device"""
        orion_version = orion.get_version()
        iot_agent_version = iotagent.get_version()
        idm_is_active = idm.is_active()
        classes = datamodel.get_classes()
        count = 0
        if orion_version != '':
            for c in classes:
                count += len(orion.get_entities(c))

        return render_template('dashboard.html', orion_version=orion_version, iot_agent_version=iot_agent_version,
                               idm_is_active=idm_is_active, registered_classes=count,
                               all_classes=len(datamodel.classes_file_list))

    @app.route('/about')
    @oidc.require_login
    def about():
        """Render About page"""
        page_name = 'About'
        page_content = 'Device Wizard is a service for registering device within N5GEH cloud platform.'
        return render_template('simple.html', page_name=page_name, page_content=page_content)

    @app.route('/help')
    @oidc.require_login
    def help():
        """Render Help page"""
        page_name = 'Help'
        page_content = 'This is a help page to explain how user can register a device in a N5GEH platform.'
        return render_template('simple.html', page_name=page_name, page_content=page_content)

    def select_type(device_types, fiware_service, render_page='select_type.html'):
        """Render Select type of device page"""
        choices = []
        for t in device_types:
            tt = t.split('.')
            choices.append((t, tt[0],))
        form = TypesForm()
        form.types.choices = choices
        return render_template(render_page, form=form, fiware_service=fiware_service)

    def wrong_device_type(device_type):
        """Render wrong device type"""
        page_name = 'Wrong device type'
        page_content = 'Could not found template for this <span class="text-warning">{}</span> device type. Please select one from <a href="/device">Device Wizard page</a>.'.format(
            device_type)
        return render_template('simple.html', page_name=page_name, page_content=page_content)

    def check_orion():
        if orion.get_version() == '':
            return ('Orion LD', 'Could not connect to the Orion LD. URL: {}'.format(orion.url),)
        return '', '',

    def check_idm():
        if not idm.is_active():
            return ('Keycloack', 'Could not connect to the Keycloack IDM. URL: {}'.format(idm.config['server']),)
        return '', '',

    def check_iotagent():
        if iotagent.get_version() == '':
            return ('IoT Agent', 'Could not connect to the IoT Agent. URL: {}'.format(iotagent.url),)
        return '', '',

    @app.route('/device', methods=['GET', 'POST'])
    @oidc.require_login
    def device():
        """Render Device Wizard page"""
        page_name, page_content = check_orion()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        page_name, page_content = check_idm()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        device_type = request.args.get('types')
        if device_type is None:
            return select_type(datamodel.device_types, 'Orion LD')

        if device_type not in datamodel.device_types:
            return wrong_device_type(device_type)

        form, properties_dict = formservice.create_form_template(device_type, orion, datamodel)

        if request.method == 'POST':
            # print(request.form)
            form = form(request.form)
            # print(form.validate())
            # for fieldName, errorMessages in form.errors.items():
            #     print(fieldName)
            #     for err in errorMessages:
            #         print(err)
            # do something with your errorMessages for fieldName
            if form.validate():
                params = {}
                for fieldname, value in form.data.items():
                    if fieldname.endswith('_datetime'):
                        params[fieldname] = value.isoformat() + 'Z'
                    else:
                        params[fieldname] = value
                    # print('{}:{}'.format(fieldname, value))

                # entity = create_local_entity('datamodel/{}'.format(device_type), params)
                entity = datamodel.create_entity(device_type, params)
                result = orion.create_entity(entity)

                id_key = properties_dict['id'][2]
                # category_key = properties_dict['category'][3]
                device_type = formservice.get_device_type(device_type)
                idm.create_entity('urn:ngsi-ld:{}:{}'.format(device_type, params[id_key]), device_type)

                if result['status']:
                    page_name = 'Success'
                    page_content = 'Entity successfully created. Go to <a href="/device">Device Wizard page</a>.'
                    return render_template('simple.html', page_name=page_name, page_content=page_content)
                else:
                    page_name = 'Failed'
                    page_content = 'Could not create entity. <a href="" onclick="windows.back()">Go Back</a> <br/>Reason: <span class="text-danger">{}</span>'.format(
                        result['error'])
                    return render_template('simple.html', page_name=page_name, page_content=page_content)

        return render_template('device.html', form=form(), action='Register', fiware_service='Orion LD')

    @app.route('/iotdevice', methods=['GET', 'POST'])
    @oidc.require_login
    def iotdevice():
        """Render Device Wizard page"""

        page_name, page_content = check_orion()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        page_name, page_content = check_iotagent()
        print(page_name)
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        page_name, page_content = check_idm()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        device_type = request.args.get('types')
        if device_type is None:
            return select_type(datamodel.iotdevice_types, 'IoT Agent')

        if device_type not in datamodel.iotdevice_types:
            return wrong_device_type(device_type)

        form = formservice.create_form_json(device_type, orion, datamodel)

        if request.method == 'POST':
            form = form(request.form)
            if form.validate():
                params = {}
                for fieldname, value in form.data.items():
                    if fieldname.endswith('_datetime'):
                        params[fieldname] = value.isoformat() + 'Z'
                    else:
                        params[fieldname] = value
                device = formservice.create_iotdevice(device_type, params, datamodel)

                result = iotagent.create_device(device)

                idm.create_entity(device['entity_name'], device['entity_type'])

                if result['status']:
                    page_name = 'Success'
                    page_content = 'Entity successfully registered. Go to <a href="/iotagent">Registered devices page</a>.'
                    return render_template('simple.html', page_name=page_name, page_content=page_content)
                else:
                    page_name = 'Failed'
                    page_content = 'Could not register entity. <a href="" onclick="windows.back()">Go Back</a> <br/>Reason: <span class="text-danger">{}</span>'.format(
                        result['error'])
                    return render_template('simple.html', page_name=page_name, page_content=page_content)

        return render_template('device.html', form=form(), action='Register', fiware_service='IoT Agent')

    @app.route('/edit', methods=['GET', 'POST'])
    @oidc.require_login
    def edit_device():
        """Edit device properties"""
        page_name, page_content = check_orion()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        device_id = request.args.get('id')
        device_type = request.args.get('type')

        form = formservice.create_form_entity(device_id, device_type, orion, datamodel)

        if request.method == 'POST':
            filled_form = form(request.form)
            if filled_form.validate():
                result = orion.update_entity(device_id, formservice.create_entity_update(filled_form.data.items()))
                if result['status']:
                    page_name = 'Success'
                    page_content = 'Entity successfully updated. Go to <a href="/orion">Registered devices page</a>.'
                    return render_template('simple.html', page_name=page_name, page_content=page_content)
                else:
                    page_name = 'Failed'
                    page_content = 'Could not update entity. <a href="" onclick="windows.back()">Go Back</a> <br/>Reason: <span class="text-danger">{}</span>'.format(
                        result['error'])
                    return render_template('simple.html', page_name=page_name, page_content=page_content)

        return render_template('device.html', form=form(), action='Update', fiware_service='Orion LD')

    @app.route('/orion', methods=['GET', 'POST'])
    @oidc.require_login
    def get_entities():
        """Render Device Wizard page"""
        page_name, page_content = check_orion()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        page_name, page_content = check_idm()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        device_type = request.args.get('types')
        if device_type is None:
            return select_type(datamodel.device_types, 'Orion LD', render_page='select_type_for_view.html')

        if device_type not in datamodel.device_types:
            return wrong_device_type(device_type)

        device_type = device_type.split(".")[0]
        devices = orion.get_entities(device_type)
        for device in devices:
            device['mqtt_topic'] = idm.create_topic(device['id'], device_type)
            device['mqtt_user'] = device['id'].lower()
        return render_template('datatable.html', devices=devices, device_type=device_type)

    @app.route('/iotagent', methods=['GET', 'POST'])
    @oidc.require_login
    def get_registered_iot_devices():
        """Render IoT Agent registered devices"""
        page_name, page_content = check_iotagent()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        page_name, page_content = check_idm()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        return render_template('iotagent.html')

    @app.route('/iotagentapi', methods=['GET', 'POST'])
    @oidc.require_login
    def get_registered_iot_devices_api():
        """Render IoT registered devices as JSON"""
        devices = iotagent.get_entities()
        for device in devices['devices']:
            device['mqtt_topic'] = idm.create_topic(device['entity_name'], device['entity_type'])
            device['mqtt_user'] = device['entity_name'].lower()
        return render_template('iotdatatable.html', devices=devices)

    @app.route('/delete', methods=['GET'])
    @oidc.require_login
    def delete():
        """Delete device from platform"""
        page_name, page_content = check_orion()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        page_name, page_content = check_idm()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)
        device_id = request.args.get('device_id')
        r = orion.delete_entity(device_id)
        idm.delete_entity(device_id)
        return "true"

    @app.route('/iotdelete', methods=['GET'])
    @oidc.require_login
    def iotdelete():
        """Delete device from platform"""
        page_name, page_content = check_iotagent()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        page_name, page_content = check_idm()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)
        device_id = request.args.get('device_id')
        iotagent.delete_entity(device_id)
        idm.delete_entity(device_id)
        return "true"

    @app.route('/init', methods=['GET'])
    @oidc.require_login
    def init():
        """Init properties for the Datamodel"""
        page_name, page_content = check_orion()
        if page_name != '':
            return render_template('simple.html', page_name=page_name, page_content=page_content)

        classes = datamodel.get_classes_files()
        for cls in classes:
            if os.path.isfile(cls):
                data = open(cls, 'rt').read()
                try:
                    result = orion.create_entity(data)
                except Exception as e:
                    pass
        page_name = 'Success'
        page_content = 'Classes successfully registered. Go to <a href="/device">Register device</a>.'
        return render_template('simple.html', page_name=page_name, page_content=page_content)

    @app.route('/logout')
    def logout():
        """Performs local logout by removing the session cookie."""
        oidc.logout()
        return redirect(app.config['IDM']['logout_link'])

    return app


if __name__ == '__main__':
    device_wizard = os.environ.get("DEVICE_WIZARD_CONFIG", default="device_wizard.json")
    client_secret = os.environ.get("CLIENT_SECRET", default="client_secrets.json")
    device_wizard_config = json.load(open(device_wizard, 'rt'))

    app = create_app(device_wizard_config, client_secret)
    app.run(host='0.0.0.0', port=8090)
