from .util import dbg, err
from os import path
import sys
import json
import copy
from .config import Config

class ConfigJson(object):
    JSON_PROFILE_NAME = "__internal_json_profile__"
    JSON_LAYOUT_NAME = "__internal_json_layout__"

    profile_to_use = 'default'
        
    def build_single_tab_layout(self, layoutjson, vertical):
        dbg ('Budiling a single tab layout from json: %s ' % layoutjson)
        
        result = {
            'root': {
                'type': 'Window'
            }
        }
        
        self.build_container_layout(layoutjson, result, 'root', 0, vertical)
        
        return result
    
    def build_multi_tab_layout(self, layoutjson, vertical):
        dbg ('Budiling multi tabs layout from json: %s ' % layoutjson)
        
        tabs = {
            'type': 'Notebook',
            'parent': 'root',
            'labels': []
        }
        
        result = {
            'root': {
                'type': 'Window'
            },
            'tabs': tabs
        }
        
        counter = 0
        
        for tab in layoutjson:
            tabs['labels'].append(tab)
            self.build_container_layout(layoutjson[tab], result, 'tabs', counter, vertical)
            counter += 1
        
        return result
    
    def build_terminal_layout(self, layoutjson, children, parent, order):
        dbg ('Building a terminal from json: %s' % layoutjson)
        
        children[parent + "." + str(order)] = {
            'type': 'Terminal',
            'order': order,
            'parent': parent,
            'profile': self.profile_to_use,
            'command': layoutjson['command']
        }
    
    def build_container_layout(self, layoutjson, children, parent, order, vertical):
        if len(layoutjson) == 1:
            layoutjson = layoutjson[0]
            
            if 'children' in layoutjson:
                self.build_container_layout(layoutjson['children'], children, parent, order, False if vertical else True)
            else:
                self.build_terminal_layout(layoutjson, children, parent, order)
            return
        
        dbg ('Building %s layout from json: %s' % ("vertical" if vertical else "horizental", layoutjson))
        
        counter = 0
        actualparent = parent
        
        for pane in layoutjson:
            if counter < (len(layoutjson) - 1):
                containername = parent + "." + str(order) + "." + str(counter)
                ratio = (100 / (len(layoutjson) - counter)) / 100
                if 'ratio' in pane:
                    ratio = pane['ratio']
                children[containername] = {
                    'type': 'VPaned' if vertical else 'HPaned',
                    'order': order + counter,
                    'ratio': ratio,
                    'parent': actualparent
                }
                actualparent = containername
            
            if 'children' in pane:
                self.build_container_layout(pane['children'], children, containername, counter, False if vertical else True)
            else:
                self.build_terminal_layout(pane, children, containername, counter)
            
            counter += 1
    
    def get_layout(self, layoutjson):
        try:
            vertical = True
            if "vertical" in layoutjson:
                vertical = layoutjson["vertical"]
                del layoutjson["vertical"]
            
            result = None
            
            if len(layoutjson) == 1:
                firstitem = next(iter(layoutjson.values()))
                result = self.build_single_tab_layout(firstitem, vertical)
            else:
                result = self.build_multi_tab_layout(layoutjson, vertical)
            
            dbg('Json layout is: %s' % result)
            return result
        except Exception as ex:
            err('Error building a layout from file %s' % ex)
            return None
    
    def get_profile(self, profilejson, baseprofile):
        try:
            result = copy.deepcopy(baseprofile)
            
            result.update(profilejson)
            
            dbg('Json profile is: %s' % result)
            return result
        except Exception as ex:
            err('Error building a profile from json file %s' % ex)
            return None
        
    def read_config(self, jsonfile):
        if not path.exists(jsonfile):
            dbg("Json config file is missing %s" % jsonfile)
            return None
        
        dbg('Loading config json from a file: %s' % jsonfile)
        
        layoutjson = None
        
        try:
            with open(jsonfile) as json_file:
                layoutjson = json.load(json_file)
        except Exception as ex:
            err('Error loading config json file %s (%s)' % (jsonfile, ex))
            return None
        
        return layoutjson

    def extend_config(self, jsonfile):
        configjson = self.read_config(jsonfile)
       
        if not configjson:
            return None
        
        config = Config()
        
        if 'profile' in configjson:
            profile = self.get_profile(configjson['profile'], config.base.profiles['default'])
            if profile:
                config.base.profiles[self.JSON_PROFILE_NAME] = profile
                self.profile_to_use = self.JSON_PROFILE_NAME
        
        if 'layout' in configjson:
            layout = self.get_layout(configjson['layout'])
            if layout:
                config.base.layouts[self.JSON_LAYOUT_NAME] = layout
                return self.JSON_LAYOUT_NAME
        
        return None
