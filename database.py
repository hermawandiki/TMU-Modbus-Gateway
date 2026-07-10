import json
import time
import os
import logging
from influxdb import InfluxDBClient

INFLUX_HOST = 'localhost'
INFLUX_PORT = 8086
INFLUX_DB = 'all_sensor_data' 
INFLUX_USER = ''      
INFLUX_PASS = ''      

GUI_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui_data.json")

FIELDS = [
    "tsu_oil_level", "tsu_oil_temp", "tsu_oil_pressure",
    "edmcr_oil_level", "edmcr_oil_temp", "edmcr_oil_pressure",
    "bus_u_temp", "bus_v_temp", "bus_w_temp",
    "wit_u_temp", "wit_v_temp", "wit_w_temp",
    "u_n_volt", "v_n_volt", "w_n_volt",
    "u_v_volt", "v_w_volt", "u_w_volt",
    "u_current", "v_current", "w_current",
    "avg_current"
]

logging.basicConfig(
    format='%(asctime)s | INFLUX: %(message)s',
    level=logging.INFO,
)

def get_latest_data():
    try:
        if not os.path.exists(GUI_DATA_FILE):
            return None
        with open(GUI_DATA_FILE, "r") as f:
            data = json.load(f)
            return data.get("values", [])
    except Exception as e:
        logging.error(f"Gagal membaca {GUI_DATA_FILE}: {e}")
        return None

def main():
    logging.info(f"Memulai database")
    client = InfluxDBClient(
        host=INFLUX_HOST, 
        port=INFLUX_PORT, 
        username=INFLUX_USER, 
        password=INFLUX_PASS, 
        database=INFLUX_DB
    )
    
    try:
        while True:
            values = get_latest_data()
            
            if values and len(values) == len(FIELDS):
                json_body = [
                    {
                        "measurement": "tmu_monitoring",
                        "tags": {
                            "location": "Surabaya",
                            "device_id": "TMU-01"
                        },
                        "fields": {}
                    }
                ]
                
                for i, field_name in enumerate(FIELDS):
                    json_body[0]["fields"][field_name] = float(values[i])
                
                try:
                    client.write_points(json_body)
                    logging.info("Berhasil mengirim 1 record ke database")
                except Exception as e:
                    logging.error(f"Gagal mengirim data: {e}")
            else:
                logging.warning("Data JSON tidak valid atau belum lengkap. Menunggu...")
                
            time.sleep(2)
            
    except KeyboardInterrupt:
        logging.info("InfluxDB Logger dihentikan oleh user.")
    finally:
        client.close()

if __name__ == "__main__":
    main()