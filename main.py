import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# --- API 설정 ---
KAKAO_API_KEY = os.environ.get("KAKAO_API_KEY")
ODSAY_API_KEY = os.environ.get("ODSAY_API_KEY")

def get_coords(address):
    # 1. 키가 잘 불러와졌는지 먼저 확인
    if not KAKAO_API_KEY:
        print("🚨 에러: Render 환경변수 KAKAO_API_KEY를 못 읽어왔어!")
        return None

    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    params = {"query": address}
    
    try:
        response = requests.get(url, headers=headers, params=params)
        res = response.json()
        
        # 2. 카카오가 보낸 진짜 응답을 로그에 찍기
        print(f"📡 카카오 응답 데이터: {res}")
        
        if 'documents' not in res:
            return None
        if not res['documents']:
            return None
            
        return float(res['documents'][0]['x']), float(res['documents'][0]['y'])
    except Exception as e:
        print(f"🚨 네트워크 에러 발생: {e}")
        return None

def get_best_meeting_place(x, y):
    """
    지하철역(SW8) -> 관광명소(AT4) -> 문화시설(CT1) 순으로 탐색
    """
    categories = ["SW8", "AT4", "CT1"]
    headers = {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}
    
    for cat in categories:
        url = f"https://dapi.kakao.com/v2/local/search/category.json?category_group_code={cat}&x={x}&y={y}&radius=3000&sort=distance"
        res = requests.get(url, headers=headers).json()
        
        if res['documents']:
            place = res['documents'][0]
            # 지하철역은 '역' 이름만, 나머지는 장소명 그대로 반환
            name = place['place_name']
            return name, float(place['x']), float(place['y'])
            
    return "적당한 상권", x, y

def get_route_info(sx, sy, ex, ey):
    url = f"https://api.odsay.com/v1/api/searchPubTransPathT?SX={sx}&SY={sy}&EX={ex}&EY={ey}&apiKey={ODSAY_API_KEY}"
    res = requests.get(url).json()
    try:
        path = res['result']['path'][0]['info']
        return path['totalTime'], path['payment']
    except:
        return 60, 1500

@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.json
    members = data.get('members', [])
    
    coords_info = []
    total_weight = 0
    
    for m in members:
        x, y = get_coords(m['address'])
        # 기동력 기반 가중치 (L1=80 ~ L5=20)
        weight = 95 - 15 * int(m['mobility']) 
        coords_info.append({'x': x, 'y': y, 'w': weight})
        total_weight += weight

    # 1. 가중치 적용 중심점 계산
    raw_x = sum(c['x'] * c['w'] for c in coords_info) / total_weight
    raw_y = sum(c['y'] * c['w'] for c in coords_info) / total_weight
    
    # 2. 만날 만한 곳으로 보정
    place_name, target_x, target_y = get_best_meeting_place(raw_x, raw_y)
    
    # 3. 실제 이동 데이터
    MIN_WAGE_MIN = 10320 / 60
    total_costs = []
    
    for c in coords_info:
        time, fee = get_route_info(c['x'], c['y'], target_x, target_y)
        total_costs.append((time * MIN_WAGE_MIN) + fee)
        
    # 4. 정산
    avg_cost = sum(total_costs) / len(total_costs)
    report = []
    for i, cost in enumerate(total_costs):
        diff = int(round(cost - avg_cost, -2))
        res = f"{abs(diff):,}원 더 부담" if diff < 0 else f"{abs(diff):,}원 혜택"
        report.append(f"멤버 {i+1}: {res}")

    return jsonify({
        "target_place": place_name,
        "report": report
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
