import os
import math
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

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
    if not GOOGLE_API_KEY: return 60, 1550
    url = (
        f"https://maps.googleapis.com/maps/api/directions/json?"
        f"origin={sy},{sx}&destination={ey},{ex}&"
        f"mode=transit&departure_time=now&language=ko&key={GOOGLE_API_KEY}"
    )
    try:
        res = requests.get(url).json()
        if res['status'] == 'OK':
            route = res['routes'][0]['legs'][0]
            dur_min = route['duration']['value'] // 60
            dist_km = route['distance']['value'] / 1000
            
            base_fare = 1550
            final_fare = base_fare
            if dist_km > 10:
                extra_dist = dist_km - 10
                final_fare += math.ceil(extra_dist / 5) * 100
            
            print(f"✅ 거리: {dist_km:.1f}km, 시간: {dur_min}분, 요금: {final_fare}원")
            return dur_min, final_fare
        else:
            return 60, 1550
    except:
        return 60, 1550

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

    tx = sum(c['x'] * c['w'] for c in coords_info) / total_weight
    ty = sum(c['y'] * c['w'] for c in coords_info) / total_weight
    place = get_best_place(tx, ty)
    
    # 여기서부터 반복문 안에서 각 멤버별로 구글 API 호출
    member_details = []
    costs = []
    for c in coords_info:
        # 멤버 각자의 좌표(c['x'], c['y'])에서 목적지(tx, ty)까지 호출
        m_time, m_fee = get_route(c['x'], c['y'], tx, ty)
        m_cost = (m_time * 172) + m_fee
        costs.append(m_cost)
        # 나중에 리포트 쓸 때 꺼내쓰기 위해 저장
        member_details.append({"time": m_time, "fee": m_fee, "total": m_cost})
        
    avg = sum(costs) / len(costs)
    
    report = []
    for i, det in enumerate(member_details):
        diff = det['total'] - avg
        status = "더 부담" if diff < 0 else "혜택"
        amount = abs(int(round(diff, -2)))
        report.append(
            f"멤버 {i+1}: 시간 {det['time']}분 / 교통비 {det['fee']}원 ➔ <b>{status} {amount}원</b>"
        )

    # 응답 데이터 (첫 번째 멤버 데이터와 리포트 전송)
    return jsonify({
        "target_place": place, 
        "avg_cost": avg, 
        "report": report, 
        "time": member_details[0]['time'], 
        "fare": member_details[0]['fee']
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
