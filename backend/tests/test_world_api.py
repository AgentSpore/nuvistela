from httpx import AsyncClient

PATH = "/api/v1/families/{}/world"


async def adult_with_child(c: AsyncClient) -> tuple[dict, dict, str, str, str]:
    r = await c.post(
        "/api/v1/families",
        json={"title": "Smiths", "display_name": "Anya Smith", "interests": ["dinosaurs"]},
    )
    fid, adult_id = r.json()["family_id"], r.json()["member"]["id"]
    adult = {"Cookie": f"bumbli_session={r.cookies['bumbli_session']}"}
    c.cookies.clear()
    r = await c.post(
        f"/api/v1/families/{fid}/members",
        headers=adult,
        json={"display_name": "Bobby", "age_band": "6-9", "role": "child", "interests": ["trains"]},
    )
    token = r.json()["invite_url"].split("#")[1]
    r = await c.post("/api/v1/invite/accept", json={"token": token})
    child = {"Cookie": f"bumbli_session={r.cookies['bumbli_session']}"}
    c.cookies.clear()
    return adult, child, fid, adult_id, r.json()["id"]


async def test_only_adult_requests_and_other_family_is_hidden(client: AsyncClient) -> None:
    adult, child, fid, *_ = await adult_with_child(client)
    other, *_ = await adult_with_child(client)
    body = {"genre": "space"}
    assert (await client.post(PATH.format(fid), headers=child, json=body)).status_code == 403
    assert (await client.post(PATH.format(fid), headers=other, json=body)).status_code == 404
    assert (await client.get(PATH.format(fid), headers=other)).status_code == 404
    assert (await client.get(PATH.format(fid), headers=adult)).status_code == 404
    assert (await client.post(PATH.format(fid), headers=adult, json=body)).status_code == 202


async def test_regenerate_is_limited_per_day(client: AsyncClient) -> None:
    adult, _, fid, *_ = await adult_with_child(client)
    await client.post(PATH.format(fid), headers=adult, json={"genre": "space"})
    codes = []
    for _ in range(4):
        r = await client.post(PATH.format(fid) + "/regenerate", headers=adult)
        codes.append(r.status_code)
    assert codes == [202, 202, 429, 429]
