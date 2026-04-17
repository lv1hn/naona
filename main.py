import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY")
ODSAY_API_KEY = os.environ.get("ODSAY_API_KEY")

def get_coords(address):
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    try:
        res = requests.get(url, headers=headers, params={"query": address}).json()
        doc = res.get('documents')[0]
        return float(doc['x']), float(doc['y'])
    except: return None

def get_best_place(x, y):
    url = f"https://dapi.kakao.com/v2/local/search/category.json?category_group_code=SW8&x={x}&y={y}&radius=3000&sort=distance"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    try:
        res = requests.get(url, headers=headers).json()
        if res.get('documents'):
            return res['documents'][0]['place_name']
    except: pass
    return "추천 중심점 근처"

def get_route(sx, sy, ex, ey):
    url = f"https://api.odsay.com/v1/api/searchPubTransPathT?SX={sx}&SY={sy}&EX={ex}&EY={ey}&apiKey={ODSAY_API_KEY}"
    try:
        res = requests.get(url).json()
        path = res['result']['path'][0]['info']
        return path['totalTime'], path['payment']
    except: return 60, 1500

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.json
    members = data.get('members', [])
    coords_info, total_weight = [], 0
    
    for m in members:
        coords = get_coords(m['address'])
        if not coords: continue
        level = int(m.get('mobility', 3))
        weight = 95 - (15 * level)
        coords_info.append({'x': coords[0], 'y': coords[1], 'w': weight})
        total_weight += weight

    if not coords_info: return jsonify({"error": "주소 오류"}), 400

    raw_x = sum(c['x'] * c['w'] for c in coords_info) / total_weight
    raw_y = sum(c['y'] * c['w'] for c in coords_info) / total_weight
    place = get_best_place(raw_x, raw_y)
    tx, ty = raw_x, raw_y
    
    costs = []
    for c in coords_info:
        # 여기가 핵심! 목적지(tx, ty)로 가는데 '각자의 출발점'에서 계산해야 함
        time, fee = get_route(c['x'], c['y'], tx, ty)
        costs.append((time * 172) + fee)
        
    avg = sum(costs) / len(costs)
    
    # 정산 금액 계산 (10원 단위에서 반올림해서 100원 단위로)
    report = []
    for i, c in enumerate(costs):
        diff = c - avg
        status = "더 부담" if diff < 0 else "혜택"
        amount = abs(int(round(diff, -2)))
        report.append(
            f"멤버 {i+1}: 시간 {time}분 / 교통비 {fee}원 ➔ <b>{status} {amount}원</b>"
        )
    return jsonify({"target_place": place, "avg_cost": avg, "report": report})
    
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
