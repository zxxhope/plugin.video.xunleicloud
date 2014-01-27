# -*- coding: utf-8 -*-
import os
import re
import gzip
import time
import json
import urllib
import urllib2
import cookielib
import captcha
from StringIO import StringIO
from xbmcswift2 import xbmc
from xbmcswift2 import Plugin
from xbmcswift2 import xbmcgui
from xbmcswift2 import xbmcplugin
try:
    from ChineseKeyboard import Keyboard
except ImportError:
    from xbmcswift2 import Keyboard

class Xunlei(object):
    def __init__(self, cookiefile):
        self.cookiejar = cookielib.LWPCookieJar()
        if os.path.exists(cookiefile):
            self.cookiejar.load(
                cookiefile, ignore_discard=True, ignore_expires=True)
        self.userid = self.getcookieatt('.xunlei.com', 'userid')
        self.sid = self.getcookieatt('.xunlei.com', 'sessionid')
        self.opener = urllib2.build_opener(
            urllib2.HTTPCookieProcessor(self.cookiejar))

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) {0}{1}'.format(
                'AppleWebKit/537.36 (KHTML, like Gecko) ',
                'Chrome/28.0.1500.71 Safari/537.36'),
            'Accept-encoding': 'gzip,deflate',
        }

    def urlopen(self, url, **args):
        if 'data' in args and type(args['data']) == dict:
            args['data'] = json.dumps(args['data'])
            #arg['data'] = urllib.urlencode(args['data'])
            self.headers['Content-Type'] = 'application/json'
        else:
            self.headers['Content-Type'] = 'application/x-www-form-urlencoded'
        rs = self.opener.open(
            urllib2.Request(url, headers=self.headers, **args), timeout=60)
        return rs

    def fetch(self,wstream):
        if wstream.headers.get('content-encoding', '') == 'gzip':
            content = gzip.GzipFile(fileobj=StringIO(wstream.read())).read()
        else:
            content = wstream.read()
        return content

    def getcookieatt(self, domain, attr):
        if domain in self.cookiejar._cookies and attr in \
           self.cookiejar._cookies[domain]['/']:
            return self.cookiejar._cookies[domain]['/'][attr].value

plugin = Plugin()
dialog = xbmcgui.Dialog()
ppath = plugin.addon.getAddonInfo('path')
cookiefile = os.path.join(ppath, 'cookie.dat')
xl = Xunlei(cookiefile)
urlpre = 'http://i.vod.xunlei.com'
cachetime = int(time.time()*1000)

@plugin.route('/')
def index():
    item = [
        {'label': '登入迅雷', 'path': plugin.url_for('login')},
        {'label': '云播空间', 'path': plugin.url_for('dashboard')},
        {'label': 'BTdigg搜索', 'path': plugin.url_for('btdigg', url='search')},
    ]
    return item

@plugin.route('/login')
def login():
    plugin.open_settings()
    user = plugin.get_setting('username')
    passwd = plugin.get_setting('password')
    if not (user and passwd):
        return

    check_url = 'http://login.xunlei.com/check?u={0}&cachetime={1}'.format(
        user, cachetime)
    login_page = xl.urlopen(check_url)
    vfcode = xl.getcookieatt('.xunlei.com', 'check_result')[2:].upper()

    if not vfcode:
        cdg = captcha.CaptchaDialog("","")
        cdg.doModal()
        confirmed = cdg.isConfirmed()
        if not confirmed:
            return
        vfcode = cdg.getText().upper()
        del cdg

    if not re.match(r'^[0-9a-f]{32}$', passwd):
        passwd = md5(md5(passwd))
    passwd = md5(passwd+vfcode)

    data = urllib.urlencode({'u': user, 'p': passwd, 'verifycode': vfcode,
                             'login_enable':'1', 'login_hour':'720',})

    login_page = xl.urlopen('http://login.xunlei.com/sec2login/', data=data)

    xl.userid = xl.getcookieatt('.xunlei.com', 'userid')
    xl.sid = xl.getcookieatt('.xunlei.com', 'sessionid')

    blogresult = xl.getcookieatt('.xunlei.com', 'blogresult')
    loginmsgs = [
        '登入成功', '验证码错误', '密码错误', '用户名不存在', '未知错误'
    ]
    plugin.notify(msg=loginmsgs[int(blogresult)])
    xl.cookiejar.save(cookiefile, ignore_discard=True)
    #for ck in xl.cookiejar:
    #    print (ck.name, ck.value)
    return

@plugin.route('/playvideo/<magnetid>')
def playvideo(magnetid):
    if 'magnet' in magnetid:
        ihash = addbt(magnetid)
    else:
        ihash = magnetid

    subbt = '%s/req_subBT/info_hash/%s/req_num/200/req_offset/0' % (
        urlpre, ihash)

    rsp = xl.urlopen(subbt)
    vfinfo = json.loads(xl.fetch(rsp))
    videos = vfinfo['resp']['subfile_list']
    if len(videos) > 1:
        selitem = dialog.select(
            '播放选择',
            [urllib2.unquote(v['name'].encode('utf-8')) for v in videos]
        )
        if selitem is -1: return
        video = videos[selitem]
    else:
        video = videos[0]
    title = urllib2.unquote(video['name'].encode('utf-8'))

    voddl = '{0}/vod_dl_all?userid={1}&gcid={2}&filename={3}&t={4}'.format(
        urlpre ,xl.userid, video['gcid'], title, cachetime)
    rsp = xl.urlopen(voddl)
    vturls = json.loads(xl.fetch(rsp))
    typ = {'Full_HD':'1080P', 'HD':'720P', 'SD':'标清'}
    vtyps = [(typ[k], v['url']) for (k, v) in vturls.iteritems() if 'url' in v]

    if not vtyps:
        plugin.notify(msg='视频转码未完成，请稍候尝试从云播空间菜单进入播放')
        return
    if len(vtyps)>1:
        selitem = dialog.select('清晰度', [v[0] for v in vtyps])
        if selitem is -1: return
        vtyp = vtyps[selitem]
    else:
        vtyp = vtyps[0]

    movurl = urllib2.urlopen(vtyp[1]).geturl()
    cks = dict((ck.name, ck.value) for ck in xl.cookiejar)
    movurl = '%s|%s&Cookie=%s' % (
        movurl, urllib.urlencode(xl.headers), urllib.urlencode(cks))

    #for ck in xl.cookiejar:
    #    print ck.name, ck.value
    listitem=xbmcgui.ListItem(label= title)
    listitem.setInfo(type="Video", infoLabels={'Title': title})
    xbmc.Player().play(movurl, listitem)
    #xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem)

@plugin.route('/dashboard')
def dashboard():
    dhurl = '%s/%s/?type=all&order=create&t=%s' % (
        urlpre, 'req_history_play_list/req_num/200/req_offset/0', cachetime)
    rsp = xl.urlopen(dhurl)
    vods = json.loads(xl.fetch(rsp))['resp']['history_play_list']

    menu = [{'label': urllib2.unquote(vod['file_name'].encode('utf-8')),
             'path': plugin.url_for('playvideo', magnetid=vod['url'][5:])
             } for vod in vods]
    return menu

@plugin.route('/btdigg/<url>')
def btdigg(url):
    if url in 'search':
        url = 'http://btdigg.org/search?q='
        kb = Keyboard('',u'请输入搜索关键字')
        kb.doModal()
        if not kb.isConfirmed(): return
        sstr = kb.getText()
        if not sstr: return
        url = url + urllib2.quote(sstr)
    else:
        url = 'http://btdigg.org' + url

    rsp = _http(url)
    rpat = re.compile(
        r'"idx">.*?>([^<]+)</a>.*?href="(magnet.*?)".*?Size:.*?">(.*?)<')
    items = rpat.findall(rsp)

    menus = [
        {'label': '%d.%s[%s]' % (s+1, v[0], v[2].replace('&nbsp;', '')),
         'path': plugin.url_for('playvideo', magnetid=v[1])}
        for s, v in enumerate(items)]
    ppat = re.compile(r'%s%s' % (
        'class="pager".*?(?:href="(/search.*?)")?>←.*?>',
        '(\d+/\d+).*?(?:href="(/search.*?)")?>Next'))

    pgs = ppat.findall(rsp)
    print pgs
    for s, p in enumerate((pgs[0][0], pgs[0][2])):
        if p:
            menus.append({'label': '上一页' if not s else '下一页',
                          'path': plugin.url_for('btdigg', url=p)})
    menus.insert(0, {'label': '[当前页%s页总共]返回上级目录' % pgs[0][1],
                     'path': plugin.url_for('index')})
    return menus

def addbt(magnetid):
    '''
    GET /req_del_list?flag=0&sessionid=sid&t=cachetime&info_hash=ihash
    Host: i.vod.xunlei.com
    '''
    urlpre = 'http://i.vod.xunlei.com'
    data = {"urls":[{"id":0,"url":magnetid}]}
    reqvideo = '%s/req_video_name?from=vlist&platform=0' % urlpre
    rsp = xl.urlopen(reqvideo, data=data)
    minfo = json.loads(xl.fetch(rsp))
    acdt = minfo['resp']['res'][0]
    data = {"urls":
            [{'id': acdt['id'], "url": acdt['url'], "name": acdt['name']},]
    }

    addvideo = '{0}/req_add_record?userid={1}&sessionid={2}&{3}'.format(
        urlpre, xl.userid, xl.sid, 'folder_id=0&from=vlist&platform=0')
    rsp = xl.urlopen(addvideo, data=data)
    acinfo = json.loads(xl.fetch(rsp))
    ihash = acinfo['resp']['res'][0]['url'][5:]
    return ihash

def md5(s):
    import hashlib
    return hashlib.md5(s).hexdigest().lower()

def _http(url):
    """
    open url
    """
    req = urllib2.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (X11; Linux x86_64) {0}{1}'.
                   format('AppleWebKit/537.36 (KHTML, like Gecko) ',
                          'Chrome/28.0.1500.71 Safari/537.36'))
    req.add_header('Accept-encoding', 'gzip,deflate')
    rsp = urllib2.urlopen(req, timeout=30)
    if rsp.info().get('Content-Encoding') == 'gzip':
        buf = StringIO(rsp.read())
        f = gzip.GzipFile(fileobj=buf)
        data = f.read()
    else:
        data = rsp.read()
    rsp.close()
    return data

if __name__ == '__main__':
    plugin.run()
