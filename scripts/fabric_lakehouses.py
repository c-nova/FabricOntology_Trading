"""Fabric lakehouse inventory/provisioning, using a caller-supplied environment token."""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.fabric.microsoft.com/v1/"
WORKSPACE = os.environ.get("WORKSPACE_ID","fb31bf6e-8199-4559-b1ce-541d04d20f04")
TOKEN = os.environ.get("FABRIC_TOKEN")
NAMES = ["LH_Group_SAP"]+[f"LH_{s}_{c}_01" for s in ("Metals","Energy","Foods","Finance") for c in ("JP","US")]


def request(path,method="GET",body=None):
    if not TOKEN:
        raise RuntimeError("Set FABRIC_TOKEN in the environment; token command-line arguments are not accepted.")
    url = path if path.startswith(BASE) else BASE+path
    if not url.startswith(BASE):
        raise RuntimeError("Refusing credential forwarding outside the Fabric API.")
    req = urllib.request.Request(url,method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization":"Bearer "+TOKEN,"Content-Type":"application/json",
                 "x-ms-fabric-skill":"spark-cli"})
    try:
        with urllib.request.urlopen(req,timeout=60) as response:
            raw=response.read()
            return response.status,response.headers,json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        # Never print request headers or credential-containing request objects.
        raise RuntimeError(f"Fabric HTTP {exc.code}; request-id={exc.headers.get('x-ms-request-id','unknown')}") from None


def inventory():
    rows, path = [], f"workspaces/{WORKSPACE}/lakehouses"
    while path:
        _,_,body=request(path)
        rows.extend(body["value"])
        path=body.get("continuationUri")
        if not path and body.get("continuationToken"):
            path=f"workspaces/{WORKSPACE}/lakehouses?continuationToken="+urllib.parse.quote(body["continuationToken"])
    return rows


def provision():
    for name in NAMES:
        matches=[x for x in inventory() if x["displayName"]==name]
        if len(matches)>1:
            raise RuntimeError("Ambiguous lakehouse name: "+name)
        if matches:
            continue
        status,headers,_=request(f"workspaces/{WORKSPACE}/items","POST",
            {"displayName":name,"type":"Lakehouse","description":"Fictional Trading demo"})
        if status==202:
            op=headers.get("x-ms-operation-id")
            if not op:
                raise RuntimeError("Ambiguous create result; inspect inventory before retrying.")
            deadline=time.monotonic()+600
            delay=int(headers.get("Retry-After","10"))
            while time.monotonic()<deadline:
                time.sleep(min(delay,60))
                _,h,result=request("operations/"+op)
                if result["status"]=="Succeeded":
                    break
                if result["status"] in ("Failed","Cancelled"):
                    raise RuntimeError("Lakehouse create failed; operation "+op)
                delay=int(h.get("Retry-After","10"))
            else:
                raise RuntimeError("Create operation deadline exceeded: "+op)
        matches=[x for x in inventory() if x["displayName"]==name]
        if len(matches)!=1:
            raise RuntimeError("Creation not verified: "+name)


if __name__=="__main__":
    try:
        if sys.argv[1:] == ["provision"]:
            provision()
        rows=inventory()
        print(json.dumps({"count":len(rows),"lakehouses":[
            {"displayName":r["displayName"],"id":r["id"]} for r in rows]},indent=2))
    except (RuntimeError,urllib.error.URLError,KeyError) as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
