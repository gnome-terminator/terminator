from .util import dbg, err
from os import path
import sys
import json
import traceback

class LayoutFile(object):
    def build_single_tab_layout(self, layoutjson, vertical):
        dbg ('Budiling a single tab layout from json: %s ' % layoutjson)
        
        result = {
            'root': {
                'type': 'Window'
            }
        }
        
        if len(layoutjson) == 1:
            self.build_terminal_layout(layoutjson, result, 'root', 0)
        else:
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
            if len(layoutjson[tab]) == 1:
                self.build_terminal_layout(layoutjson[tab][0], result, 'tabs', counter)
            else:
                self.build_container_layout(layoutjson[tab], result, 'tabs', counter, vertical)
            counter += 1
        
        return result
    
    def build_terminal_layout(self, layoutjson, children, parent, order):
        dbg ('Building a terminal from json: %s' % layoutjson)
        
        children[parent + "." + str(order)] = {
            'type': 'Terminal',
            'order': order,
            'parent': parent,
            'command': layoutjson['command']
        }
    
    def build_container_layout(self, layoutjson, children, parent, order, vertical):
        dbg ('Building %s layout from json: %s' % ("vertical" if vertical else "horizental", layoutjson))
        
        counter = 0
        actualparent = parent
        
        for pane in layoutjson:
            if counter < (len(layoutjson) - 1):
                containername = parent + "." + str(order) + "." + str(counter)
                ratio = (100 / (len(layoutjson) - counter)) / 100
                children[containername] = {
                    'type': 'VPaned' if vertical else 'HPaned',
                    'order': order + counter,
                    'ratio': round(ratio, 2),
                    'parent': actualparent
                }
                actualparent = containername
            
            if 'children' in pane:
                if len(pane['children']) == 1:
                    self.build_terminal_layout(pane, pane['children'], containername, counter)
                else:
                    self.build_container_layout(pane['children'], children, containername, counter, False if vertical else True)
            else:
                self.build_terminal_layout(pane, children, containername, counter)
            
            counter += 1
    
    def get_layout_file(self, layoutname):
        if (not path.exists(layoutname)):
            return None
        
        dbg('Loading layout from a file: %s' % layoutname)
        
        layoutjson = None
        
        try:
            with open(layoutname) as json_file:
                layoutjson = json.load(json_file)
        except Exception as ex:
            err('Error loading layout file %s (%s)' % (layoutname, ex))
            return None
        
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
            err('Error building a layout from file %s (%s)' % (layoutname, ex))
            traceback.print_exc(ex)
            return None
