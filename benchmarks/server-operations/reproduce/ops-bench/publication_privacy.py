"""Deterministic data scrubbing; private rules never become public artifacts."""
import hashlib, json, re

SENSITIVE_KEYS={'api_key','api-key','password','private_key','private-key','approval','approval_token','owner_grant','signed_grant','grant_token','signing_secret','signing_key','bearer_token','access_token','refresh_token'}
FINGERPRINT=re.compile(r'SHA256:[A-Za-z0-9+/]{20,}={0,3}')
PEM=re.compile(r'-----BEGIN [^-\n]*PRIVATE KEY-----.*?-----END [^-\n]*PRIVATE KEY-----',re.S)
BEARER=re.compile(r'(?i)\bBearer[ \t]+[A-Za-z0-9._~+/=-]+')

def json_bytes(value):return (json.dumps(value,indent=2,ensure_ascii=True)+'\n').encode()

class Scrubber:
    def __init__(self,rules):
        self.replacements=sorted(rules.get('replacements',{}).items(),key=lambda item:-len(item[0]))
        self.secrets=[s for s in rules.get('secrets',[]) if isinstance(s,str) and s]
        self.excluded_home_roots=rules.get('excluded_home_roots',[])
        self.stats={'identity_replacements':0,'secret_replacements':0,'sensitive_fields':0,'fingerprints':0,'private_key_blocks':0,'bearer_headers':0}

    def string(self,text):
        for secret in self.secrets:
            count=text.count(secret)
            if count:self.stats['secret_replacements']+=count;text=text.replace(secret,'[REDACTED]')
        for original,replacement in self.replacements:
            count=text.count(original)
            if count:self.stats['identity_replacements']+=count;text=text.replace(original,replacement)
        def fingerprint(match):
            self.stats['fingerprints']+=1
            return 'SHA256:TEST_KEY_'+hashlib.sha256(match.group().encode()).hexdigest()[:16]
        text=FINGERPRINT.sub(fingerprint,text)
        text,count=PEM.subn('[PRIVATE_KEY_REDACTED]',text);self.stats['private_key_blocks']+=count
        text,count=BEARER.subn('Bearer [REDACTED]',text);self.stats['bearer_headers']+=count
        # Model messages frequently embed JSON tool arguments as strings.
        stripped=text.strip()
        if stripped.startswith(('{','[')):
            try:value=json.loads(stripped)
            except json.JSONDecodeError:pass
            else:
                if isinstance(value,(dict,list)):return json.dumps(self.value(value),ensure_ascii=True)
        return text

    def value(self,value):
        if isinstance(value,dict):
            result={}
            for key,item in value.items():
                if key.lower() in SENSITIVE_KEYS and isinstance(item,str) and item:
                    self.stats['sensitive_fields']+=1;result[key]='[REDACTED]'
                else:result[key]=self.value(item)
            return result
        if isinstance(value,list):return [self.value(item) for item in value]
        if isinstance(value,str):return self.string(value)
        return value

    def check(self,value):
        def strings(item):
            if isinstance(item,dict):
                for k,v in item.items():yield str(k);yield from strings(v)
            elif isinstance(item,list):
                for v in item:yield from strings(v)
            elif isinstance(item,str):yield item
        for text in strings(value):
            if any(s in text for s in self.secrets):raise ValueError('Configured private secret remains')
            if any(original in text for original,_ in self.replacements):raise ValueError('Configured private identity remains')
            if any(root in text for root in self.excluded_home_roots):raise ValueError('Private home root remains')
            if PEM.search(text):raise ValueError('Private key block remains')
            # Placeholder is deliberately outside the bearer-value regex.
            if BEARER.search(text):raise ValueError('Bearer [REDACTED] remains')

def sanitize_record(record,original_sha256,scrubber):
    clean=scrubber.value(record)
    clean['publication_provenance']={'as_tested_original_record_sha256':original_sha256,'privacy_transform':'Operator-configured identity/secret redaction, stable host-identity and test-key fingerprint pseudonyms. Timings, equality/state predicates and independent review decisions retained.'}
    scrubber.check(clean)
    return clean
