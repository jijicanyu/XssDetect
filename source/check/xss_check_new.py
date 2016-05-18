#_*_coding:utf-8_*_
import requests, re, urllib, random, string,urllib2

'''
re.sub(pattern, repl, string, max=0) 以正则为基础，在string中，把pattern替换成repl
re.sub('[abc]', 'o', 'Mark')--》'Mork'  。

str.replace(old, new[, max]) 把字符串中的 old 替换成 new ，替换不超过 max 次。

re.finditer(pattern, string, flags=0) 返回一个迭代器,可以一个一个的得到匹配返回的 Match对象。这在对每次返回的对象进行比较复杂的操作时比较有用。

re.search(pattern, string, flags=0) 扫描整个字符串并返回第一个成功的匹配。 re.I 使匹配对大小写不敏感

re.escape(string) 对字符串中的非字母数字进行转义

strip() 方法用于移除字符串头尾指定的字符（默认为空格）。
'''

PREFIX_SUFFIX_LENGTH = 5
SMALLER_CHAR_POOL = ('<', '>')
LARGER_CHAR_POOL = ('\'', '"', '>', '<', ';')
GET, POST = "GET", "POST"

DOM_FILTER_REGEX = r"(?s)<!--.*?-->|\bescape\([^)]+\)|\([^)]+==[^(]+\)|\"[^\"]+\"|'[^']+'"
DOM_PATTERNS = (
    r"(?s)<script[^>]*>[^<]*?(var|\n)\s*(\w+)\s*=[^;]*(document\.(location|URL|documentURI)|location\.(href|search)|window\.location)[^;]*;[^<]*(document\.write(ln)?\(|\.innerHTML\s*=|eval\(|setTimeout\(|setInterval\(|location\.(replace|assign)\(|setAttribute\()[^;]*\2.*?</script>",
    r"(?s)<script[^>]*>[^<]*?(document\.write\(|\.innerHTML\s*=|eval\(|setTimeout\(|setInterval\(|location\.(replace|assign)\(|setAttribute\()[^;]*(document\.(location|URL|documentURI)|location\.(href|search)|window\.location).*?</script>",
)

REGULAR_PATTERNS = (
    (r"\A[^<>]*%(chars)s[^<>]*\Z", ('<', '>'), "\".xss.\", pure text response, %(filtering)s filtering", None),
    (r"<!--[^>]*%(chars)s|%(chars)s[^<]*-->", ('<', '>'), "\"<!--.'.xss.'.-->\", inside the comment, %(filtering)s filtering", None),
    (r"(?s)<script[^>]*>[^<]*?'[^<']*%(chars)s|%(chars)s[^<']*'[^<]*</script>", ('\'', ';'), "\"<script>.'.xss.'.</script>\", enclosed by <script> tags, inside single-quotes, %(filtering)s filtering", None),
    (r'(?s)<script[^>]*>[^<]*?"[^<"]*%(chars)s|%(chars)s[^<"]*"[^<]*</script>', ('"', ';'), "'<script>.\".xss.\".</script>', enclosed by <script> tags, inside double-quotes, %(filtering)s filtering", None),
    (r"(?s)<script[^>]*>[^<]*?%(chars)s|%(chars)s[^<]*</script>", (';',), "\"<script>.xss.</script>\", enclosed by <script> tags, %(filtering)s filtering", None),
    (r">[^<]*%(chars)s[^<]*(<|\Z)", ('<', '>'), "\">.xss.<\", outside of tags, %(filtering)s filtering", r"(?s)<script.+?</script>|<!--.*?-->"),
    (r"<[^>]*'[^>']*%(chars)s[^>']*'[^>]*>", ('\'',), "\"<.'.xss.'.>\", inside the tag, inside single-quotes, %(filtering)s filtering", r"(?s)<script.+?</script>|<!--.*?-->"),
    (r'<[^>]*"[^>"]*%(chars)s[^>"]*"[^>]*>', ('"',), "'<.\".xss.\".>', inside the tag, inside double-quotes, %(filtering)s filtering", r"(?s)<script.+?</script>|<!--.*?-->"),
    (r"<[^>]*%(chars)s[^>]*>", (), "\"<.xss.>\", inside the tag, outside of quotes, %(filtering)s filtering", r"(?s)<script.+?</script>|<!--.*?-->"),
)

_headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/48.0.2564.116 Safari/537.36'}
TIMEOUT = 3  


# 请求url，返回网页源码
def _retrieve_content(url, data=None):
	# 把url里面的空格进行urlencode
	new_url = "".join(url[i].replace(' ', "%20") if i > url.find('?') else url[i] for i in xrange(len(url)))
	try:
		req = urllib2.Request(new_url, data, _headers)
		retval = urllib2.urlopen(req, timeout=TIMEOUT).read()
	except Exception, ex:
		retval = ex.read() if hasattr(ex, "read") else getattr(ex, "msg", str())

	return retval or ""


def _contains(content, chars):
    content = re.sub(r"\\[%s]" % re.escape("".join(chars)), "", content) if chars else content
    return all(char in content for char in chars)

#整合GET POST
def do_xss_check(url, data=None):
    url, data = re.sub(r"=(&|\Z)", "=1\g<1>", url) if url else url, re.sub(r"=(&|\Z)", "=1\g<1>", data) if data else data
    try:
        for phase in (GET, POST):
            current = url if phase is GET else (data or "")
            for match in re.finditer(r"((\A|[?&])(?P<parameter>[\w\[\]]+)=)(?P<value>[^&#]+)", current):#正则匹配参数，如：?page=90&id=34
                found, usable = False, True
                prefix, suffix = ("".join(random.sample(string.ascii_lowercase, PREFIX_SUFFIX_LENGTH)) for i in xrange(2))#随机生成5个字母的前缀和后缀字母
                for pool in (LARGER_CHAR_POOL, SMALLER_CHAR_POOL):
                    if not found:
                    	# tampered 是把上面获取的参数进行替换，domain+参数+[']前缀+随机pool+后缀，最后吧所有参数都url编码
                    	# eg: ?page=8890%27tnmow%3C%3E%27%3B%22ukenc&id=34#at123 （?page=8890'tnmow<>';"ukenc&id=34#at123）
                        tampered = current.replace(match.group(0), "%s%s" % (match.group(0), urllib.quote("%s%s%s%s" % ("'" if pool == LARGER_CHAR_POOL else "", prefix, "".join(random.sample(pool, len(pool))), suffix))))
                        # 获取攻击之后的源码content
                        content = (_retrieve_content(tampered, data) if phase is GET else _retrieve_content(url, tampered)).replace("%s%s" % ("'" if pool == LARGER_CHAR_POOL else "", prefix), prefix)
                        for sample in re.finditer("%s([^ ]+?)%s" % (prefix, suffix), content, re.I):
                            for regex, condition, info, content_removal_regex in REGULAR_PATTERNS: #这里循环输出REGULAR_PATTERNS规律，进行匹配相关字段
                            	# 使用正则 \A[^<>]*%(chars)s[^<>]*\Z  合并chars(rdjeo\;\"\>\<\'gqejn)之后，进行对返回源进行匹配eg: \A[^<>]*tnmow\;\"\>\<\'ukenc[^<>]*\Z
                                context = re.search(regex % {"chars": re.escape(sample.group(0))}, re.sub(content_removal_regex or "", "", content), re.I)
                                if context and not found and sample.group(1).strip():
                                    if _contains(sample.group(1), condition):
                                    	return match.group("parameter"),url
                                        found = True                                        
                                    break
        if not usable:
            return "no usable GET/POST parameters found"
    except KeyboardInterrupt:
        return
#    return retval

# dom xss 检测
def do_dom_xss_check(url):
    url = re.sub(r"=(&|\Z)", "=1\g<1>", url) if url else url 
    content = requests.get(url).text
    original = re.sub(DOM_FILTER_REGEX, "",content)
    dom = max(re.search(_, original) for _ in DOM_PATTERNS)
    if dom:
        return dom.group(0),url


url = "http://127.0.0.1/cms/show.php?id=35"
q = do_xss_check(url)
print q
