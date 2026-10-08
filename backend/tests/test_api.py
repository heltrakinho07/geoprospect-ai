AOI={"type":"Polygon","coordinates":[[[32,-19],[33,-19],[33,-18],[32,-18],[32,-19]]]}

def register(client,email,name):
    r=client.post("/v1/auth/register",json={"email":email,"password":"StrongTesting123!","organization_name":name})
    assert r.status_code==201,r.text
    return r.json()

def header(user):
    return {"Authorization":"Bearer "+user["access_token"]}

def test_health(client):
    assert client.get("/health").json()["status"]=="ok"
    assert client.get("/health/ready").status_code==200

def test_auth_and_isolation(client):
    a=register(client,"alice@company.test","Company A")
    b=register(client,"bob@company.test","Company B")
    org_a=a["organization"]["id"];org_b=b["organization"]["id"]
    p=client.post(f"/v1/orgs/{org_a}/projects",json={"name":"Manica study","aoi_geojson":AOI,"target_mineral":"gold"},headers=header(a))
    assert p.status_code==201,p.text
    project=p.json()["id"]
    assert len(client.get(f"/v1/orgs/{org_a}/projects",headers=header(a)).json())==1
    assert client.get(f"/v1/orgs/{org_a}/projects",headers=header(b)).status_code==404
    assert client.get(f"/v1/orgs/{org_a}/projects/{project}",headers=header(b)).status_code==404
    assert client.post(f"/v1/orgs/{org_a}/projects/{project}/datasets",json={"name":"Observations","geojson":{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Point","coordinates":[32.5,-18.5]}}]}},headers=header(b)).status_code==404
    assert client.get(f"/v1/orgs/{org_b}/projects",headers=header(b)).json()==[]

def test_invalid_aoi(client):
    a=register(client,"geo@company.test","Geo")
    r=client.post(f"/v1/orgs/{a['organization']['id']}/projects",json={"name":"Bad","aoi_geojson":{"type":"Point","coordinates":[33,-19]}},headers=header(a))
    assert r.status_code==422

def test_login_invalid_credentials(client):
    register(client,"user@company.test","User Co")
    assert client.post("/v1/auth/login",json={"email":"user@company.test","password":"not-it"}).status_code==401
    assert client.get("/v1/me").status_code==401
