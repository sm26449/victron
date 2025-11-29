#!/usr/bin/env python3
"""
Fronius Modbus Register Scanner

Scans all known SunSpec registers for each device and saves to JSON.
Helps understand what data is available and which registers to poll.
"""

import json
import time
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# Configuration
MODBUS_HOST = "192.168.88.240"
MODBUS_PORT = 502
TIMEOUT = 3
DEVICE_IDS = [1, 2, 3, 4, 240]  # Inverters 1-4 and Meter 240

# SunSpec register definitions for Fronius
# Format: (start_address, count, name, description)
REGISTER_BLOCKS = [
    # Common Model (Model 1) - Device identification
    (40001, 2, "SunSpec_ID", "SunSpec identifier 'SunS'"),
    (40003, 1, "SunSpec_DID", "SunSpec Device ID"),
    (40004, 1, "SunSpec_Length", "Model length"),
    (40005, 16, "Manufacturer", "Manufacturer name"),
    (40021, 16, "Model", "Device model"),
    (40037, 8, "Options", "Options"),
    (40045, 8, "Version", "Software version"),
    (40053, 16, "Serial", "Serial number"),
    (40069, 1, "DeviceAddress", "Modbus device address"),

    # Inverter Model (101/102/103) - starts at 40070
    (40070, 1, "ID", "Model ID (101=single, 102=split, 103=3phase)"),
    (40071, 1, "L", "Model length"),
    (40072, 1, "A", "AC Total Current"),
    (40073, 1, "AphA", "AC Phase A Current"),
    (40074, 1, "AphB", "AC Phase B Current"),
    (40075, 1, "AphC", "AC Phase C Current"),
    (40076, 1, "A_SF", "Current scale factor"),
    (40077, 1, "PPVphAB", "AC Voltage Phase AB"),
    (40078, 1, "PPVphBC", "AC Voltage Phase BC"),
    (40079, 1, "PPVphCA", "AC Voltage Phase CA"),
    (40080, 1, "PhVphA", "AC Voltage Phase A"),
    (40081, 1, "PhVphB", "AC Voltage Phase B"),
    (40082, 1, "PhVphC", "AC Voltage Phase C"),
    (40083, 1, "V_SF", "Voltage scale factor"),
    (40084, 1, "W", "AC Power"),
    (40085, 1, "W_SF", "Power scale factor"),
    (40086, 1, "Hz", "AC Frequency"),
    (40087, 1, "Hz_SF", "Frequency scale factor"),
    (40088, 1, "VA", "Apparent Power"),
    (40089, 1, "VA_SF", "Apparent Power scale factor"),
    (40090, 1, "VAr", "Reactive Power"),
    (40091, 1, "VAr_SF", "Reactive Power scale factor"),
    (40092, 1, "PF", "Power Factor"),
    (40093, 1, "PF_SF", "Power Factor scale factor"),
    (40094, 2, "WH", "AC Lifetime Energy (acc32)"),
    (40096, 1, "WH_SF", "Energy scale factor"),
    (40097, 1, "DCA", "DC Current"),
    (40098, 1, "DCA_SF", "DC Current scale factor"),
    (40099, 1, "DCV", "DC Voltage"),
    (40100, 1, "DCV_SF", "DC Voltage scale factor"),
    (40101, 1, "DCW", "DC Power"),
    (40102, 1, "DCW_SF", "DC Power scale factor"),
    (40103, 1, "TmpCab", "Cabinet Temperature"),
    (40104, 1, "TmpSnk", "Heat Sink Temperature"),
    (40105, 1, "TmpTrns", "Transformer Temperature"),
    (40106, 1, "TmpOt", "Other Temperature"),
    (40107, 1, "Tmp_SF", "Temperature scale factor"),
    (40108, 1, "St", "Operating State"),
    (40109, 1, "StVnd", "Vendor State"),
    (40110, 2, "Evt1", "Event Flags 1"),
    (40112, 2, "Evt2", "Event Flags 2"),
    (40114, 2, "EvtVnd1", "Vendor Event 1"),
    (40116, 2, "EvtVnd2", "Vendor Event 2"),
    (40118, 2, "EvtVnd3", "Vendor Event 3"),
    (40120, 2, "EvtVnd4", "Vendor Event 4"),

    # MPPT Model (Model 160) - Multiple strings DC data
    (40122, 1, "ID_MPPT", "MPPT Model ID (should be 160)"),
    (40123, 1, "L_MPPT", "MPPT Model length"),

    # Extended MPPT registers (if model 160 exists)
    (40266, 1, "MPPT_ID", "MPPT Model ID"),
    (40267, 1, "MPPT_L", "MPPT Model Length"),
    (40268, 1, "MPPT_DCA_SF", "MPPT DC Current SF"),
    (40269, 1, "MPPT_DCV_SF", "MPPT DC Voltage SF"),
    (40270, 1, "MPPT_DCW_SF", "MPPT DC Power SF"),
    (40271, 1, "MPPT_DCWH_SF", "MPPT DC Energy SF"),
    (40272, 1, "MPPT_N", "Number of MPPT modules"),
    (40273, 1, "MPPT_TmsPer", "Timestamp period"),
    (40274, 2, "MPPT_Evt", "MPPT Global Events"),

    # MPPT Module 1
    (40276, 1, "M1_ID", "Module 1 ID"),
    (40277, 2, "M1_IDStr", "Module 1 String ID"),
    (40279, 1, "M1_DCA", "Module 1 DC Current"),
    (40280, 1, "M1_DCV", "Module 1 DC Voltage"),
    (40281, 1, "M1_DCW", "Module 1 DC Power"),
    (40282, 2, "M1_DCWH", "Module 1 Lifetime Energy"),
    (40284, 1, "M1_Tms", "Module 1 Timestamp"),
    (40285, 1, "M1_Tmp", "Module 1 Temperature"),
    (40286, 1, "M1_St", "Module 1 Status"),
    (40287, 2, "M1_Evt", "Module 1 Events"),

    # MPPT Module 2
    (40289, 1, "M2_ID", "Module 2 ID"),
    (40290, 2, "M2_IDStr", "Module 2 String ID"),
    (40292, 1, "M2_DCA", "Module 2 DC Current"),
    (40293, 1, "M2_DCV", "Module 2 DC Voltage"),
    (40294, 1, "M2_DCW", "Module 2 DC Power"),
    (40295, 2, "M2_DCWH", "Module 2 Lifetime Energy"),

    # Meter Model (201/202/203/204) - if meter exists
    # These would start after inverter model ends
]

# Meter-specific registers (Model 201-204)
METER_REGISTERS = [
    (40070, 1, "M_ID", "Meter Model ID"),
    (40071, 1, "M_L", "Meter Model Length"),
    (40072, 1, "M_A", "Total AC Current"),
    (40073, 1, "M_AphA", "Phase A Current"),
    (40074, 1, "M_AphB", "Phase B Current"),
    (40075, 1, "M_AphC", "Phase C Current"),
    (40076, 1, "M_A_SF", "Current SF"),
    (40077, 1, "M_PhV", "LN Voltage Avg"),
    (40078, 1, "M_PhVphA", "Phase A-N Voltage"),
    (40079, 1, "M_PhVphB", "Phase B-N Voltage"),
    (40080, 1, "M_PhVphC", "Phase C-N Voltage"),
    (40081, 1, "M_PPV", "LL Voltage Avg"),
    (40082, 1, "M_PPVphAB", "Phase A-B Voltage"),
    (40083, 1, "M_PPVphBC", "Phase B-C Voltage"),
    (40084, 1, "M_PPVphCA", "Phase C-A Voltage"),
    (40085, 1, "M_V_SF", "Voltage SF"),
    (40086, 1, "M_Hz", "Frequency"),
    (40087, 1, "M_Hz_SF", "Frequency SF"),
    (40088, 1, "M_W", "Total Real Power"),
    (40089, 1, "M_WphA", "Phase A Power"),
    (40090, 1, "M_WphB", "Phase B Power"),
    (40091, 1, "M_WphC", "Phase C Power"),
    (40092, 1, "M_W_SF", "Power SF"),
    (40093, 1, "M_VA", "Total Apparent Power"),
    (40094, 1, "M_VAphA", "Phase A VA"),
    (40095, 1, "M_VAphB", "Phase B VA"),
    (40096, 1, "M_VAphC", "Phase C VA"),
    (40097, 1, "M_VA_SF", "VA SF"),
    (40098, 1, "M_VAR", "Total Reactive Power"),
    (40099, 1, "M_VARphA", "Phase A VAR"),
    (40100, 1, "M_VARphB", "Phase B VAR"),
    (40101, 1, "M_VARphC", "Phase C VAR"),
    (40102, 1, "M_VAR_SF", "VAR SF"),
    (40103, 1, "M_PF", "Average Power Factor"),
    (40104, 1, "M_PFphA", "Phase A PF"),
    (40105, 1, "M_PFphB", "Phase B PF"),
    (40106, 1, "M_PFphC", "Phase C PF"),
    (40107, 1, "M_PF_SF", "PF SF"),
    (40108, 2, "M_TotWhExp", "Total Exported Energy"),
    (40110, 2, "M_TotWhExpPhA", "Phase A Exported"),
    (40112, 2, "M_TotWhExpPhB", "Phase B Exported"),
    (40114, 2, "M_TotWhExpPhC", "Phase C Exported"),
    (40116, 2, "M_TotWhImp", "Total Imported Energy"),
    (40118, 2, "M_TotWhImpPhA", "Phase A Imported"),
    (40120, 2, "M_TotWhImpPhB", "Phase B Imported"),
    (40122, 2, "M_TotWhImpPhC", "Phase C Imported"),
    (40124, 1, "M_TotWh_SF", "Energy SF"),
]


# --- Funcții de Decodare ---

def decode_string(registers):
    """Decode ASCII string from registers"""
    bytes_data = b''
    for reg in registers:
        # '>H' - Big Endian, Unsigned Short (16-bit)
        bytes_data += struct.pack('>H', reg)
    return bytes_data.decode('ascii', errors='ignore').rstrip('\x00 ')


def decode_int16(value):
    """Convert uint16 to signed int16 (Scale Factors)"""
    # 0x8000 = Not Implemented (N/A)
    if value == 0x8000:
        return None
    # Verifică dacă este număr negativ (bitul 15 setat)
    if value >= 0x8000:
        return value - 0x10000
    return value


def decode_uint32(regs):
    """Decode 32-bit unsigned from two registers (MSW, LSW)"""
    if len(regs) < 2:
        return None
    # MSW (Most Significant Word) * 2^16 | LSW (Least Significant Word)
    value = (regs[0] << 16) | regs[1]
    # 0xFFFFFFFF = Not Implemented (N/A)
    if value == 0xFFFFFFFF:
        return None
    return value

# --- Funcție Principală de Scanare ---

def scan_device(client, device_id, is_meter=False):
    """Scan all registers for a device"""
    print(f"\n{'='*60}")
    print(f"Scanning Device ID: {device_id}")
    print(f"{'='*60}")

    result = {
        "device_id": device_id,
        "scan_time": datetime.now().isoformat(),
        "registers": {},
        "raw_blocks": {},
        "errors": []
    }

    # 1. Citiți blocul comun (40001 - 40069)
    # Adresa de pornire: 40001, care este offset 0 în Modbus.
    COMMON_START_ADDR = 0 
    COMMON_COUNT = 69
    
    print(f"Reading identification registers (40001-40069) from offset {COMMON_START_ADDR}...")
    try:
        # CORECTIE CRITICĂ: address=0 (pentru 40001)
        response = client.read_holding_registers(address=COMMON_START_ADDR, count=COMMON_COUNT, slave=device_id)
        if response.isError():
            result["errors"].append(f"Failed to read identification: {response}")
            print(f"  ERROR: {response}")
            return result

        regs = response.registers
        result["raw_blocks"][f"40001-400{40000 + COMMON_COUNT}"] = regs

        # Parsare identificare (indexarea este corectă pe lista regs)
        # 40001, 40002 -> regs[0], regs[1]
        sunspec_id = decode_uint32(regs[0:2]) 
        
        # 'SunS' (0x53756E53)
        if sunspec_id is None or sunspec_id != 0x53756E53:
            result["errors"].append(f"Invalid SunSpec ID: {hex(sunspec_id or 0)}")
            print(f"  ERROR: Invalid SunSpec ID: {hex(sunspec_id or 0)}")
            return result

        result["registers"]["40001"] = {"name": "SunSpec_ID", "value": hex(sunspec_id), "description": "SunSpec 'SunS'"}
        result["registers"]["40003"] = {"name": "SunSpec_DID", "value": regs[2], "description": "Common Model DID"}
        result["registers"]["40004"] = {"name": "SunSpec_Length", "value": regs[3], "description": "Model length"}

        # Adresele sunt: 40005 (index 4) până la 40020 (index 19) => regs[4:20]
        manufacturer = decode_string(regs[4:20])
        model = decode_string(regs[20:36])
        version = decode_string(regs[44:52])
        serial = decode_string(regs[52:68])

        result["registers"]["40005"] = {"name": "Manufacturer", "value": manufacturer, "description": "Manufacturer name"}
        result["registers"]["40021"] = {"name": "Model", "value": model, "description": "Device model"}
        result["registers"]["40045"] = {"name": "Version", "value": version, "description": "Firmware version"}
        result["registers"]["40053"] = {"name": "Serial", "value": serial, "description": "Serial number"}
        result["registers"]["40069"] = {"name": "DeviceAddress", "value": regs[68], "description": "Modbus address"}

        print(f"  Manufacturer: {manufacturer}")
        print(f"  Model: {model}")
        print(f"  Serial: {serial}")
        print(f"  Version: {version}")

    except Exception as e:
        result["errors"].append(f"Exception reading identification: {str(e)}")
        print(f"  EXCEPTION: {e}")
        return result

    time.sleep(0.5)

    # 2. Citiți blocul de măsurare (40070+)
    # Adresa de pornire: 40070, care este offset 69 (40070 - 40001)
    MEASUREMENT_START_ADDR = 69
    MEASUREMENT_COUNT = 55 # Acoperă până la 40124
    
    print(f"Reading measurement registers (40070-40124) from offset {MEASUREMENT_START_ADDR}...")
    try:
        # CORECTIE CRITICĂ: address=69 (pentru 40070)
        response = client.read_holding_registers(address=MEASUREMENT_START_ADDR, count=MEASUREMENT_COUNT, slave=device_id)
        if response.isError():
            result["errors"].append(f"Failed to read measurements: {response}")
            print(f"  ERROR: {response}")
        else:
            regs = response.registers
            result["raw_blocks"][f"40070-40{40069 + MEASUREMENT_COUNT}"] = regs

            # 40070 este regs[0]
            model_id = regs[0]
            result["registers"]["40070"] = {"name": "Model_ID", "value": model_id, "description": "SunSpec Model ID"}
            print(f"  Model ID: {model_id}")

            # Parsare Inverter
            if model_id in [101, 102, 103]:
                print(f"  Device Type: Inverter (Model {model_id})")
                result["device_type"] = "inverter"
                result["model_id"] = model_id

                inv_regs = [
                    (40071, "L", "Model length"), (40072, "A", "AC Total Current"), (40073, "AphA", "AC Phase A Current"),
                    (40074, "AphB", "AC Phase B Current"), (40075, "AphC", "AC Phase C Current"), (40076, "A_SF", "Current scale factor"),
                    (40077, "PPVphAB", "AC Voltage AB"), (40078, "PPVphBC", "AC Voltage BC"), (40079, "PPVphCA", "AC Voltage CA"),
                    (40080, "PhVphA", "AC Voltage AN"), (40081, "PhVphB", "AC Voltage BN"), (40082, "PhVphC", "AC Voltage CN"),
                    (40083, "V_SF", "Voltage SF"), (40084, "W", "AC Power"), (40085, "W_SF", "Power SF"),
                    (40086, "Hz", "Frequency"), (40087, "Hz_SF", "Frequency SF"), (40088, "VA", "Apparent Power"),
                    (40089, "VA_SF", "VA SF"), (40090, "VAr", "Reactive Power"), (40091, "VAr_SF", "VAR SF"),
                    (40092, "PF", "Power Factor"), (40093, "PF_SF", "PF SF"),
                ]

                for addr, name, desc in inv_regs:
                    idx = addr - 40070 # Indexul corect (0-based) în lista regs
                    if idx < len(regs):
                        val = regs[idx]
                        if "_SF" in name:
                            val = decode_int16(val)
                        result["registers"][str(addr)] = {"name": name, "value": val, "description": desc}

                # Energie (32-bit): 40094-40095 (regs[24:26])
                if len(regs) > 25:
                    wh = decode_uint32(regs[24:26])
                    result["registers"]["40094"] = {"name": "WH", "value": wh, "description": "Lifetime Energy (Wh)"}

                # DC values și Status (40097+)
                # Logica de parsare rămasă este corectă, folosind diferența de adresă (idx = addr - 40070)
                dc_regs = [
                    (40097, "DCA", "DC Current"), (40098, "DCA_SF", "DC Current SF"), (40099, "DCV", "DC Voltage"),
                    (40100, "DCV_SF", "DC Voltage SF"), (40101, "DCW", "DC Power"), (40102, "DCW_SF", "DC Power SF"),
                ]
                for addr, name, desc in dc_regs:
                    idx = addr - 40070
                    if idx < len(regs):
                        val = regs[idx]
                        if "_SF" in name:
                            val = decode_int16(val)
                        result["registers"][str(addr)] = {"name": name, "value": val, "description": desc}

                status_regs = [
                    (40103, "TmpCab", "Cabinet Temp"), (40104, "TmpSnk", "Heatsink Temp"),
                    (40105, "TmpTrns", "Transformer Temp"), (40106, "TmpOt", "Other Temp"),
                    (40107, "Tmp_SF", "Temp SF"), (40108, "St", "Operating State"),
                    (40109, "StVnd", "Vendor State"),
                ]
                for addr, name, desc in status_regs:
                    idx = addr - 40070
                    if idx < len(regs):
                        val = regs[idx]
                        if "_SF" in name:
                            val = decode_int16(val)
                        result["registers"][str(addr)] = {"name": name, "value": val, "description": desc}

            # Parsare Meter (Logică similară de indexare ar fi necesară, dar o simplificăm pentru acest scaner)
            elif model_id in [201, 202, 203, 204]:
                print(f"  Device Type: Meter (Model {model_id})")
                result["device_type"] = "meter"
                result["model_id"] = model_id
                # Puteți adăuga aici o buclă de parsare completă pentru METER_REGISTERS dacă este necesar

    except Exception as e:
        result["errors"].append(f"Exception reading measurements: {str(e)}")
        print(f"  EXCEPTION: {e}")

    time.sleep(0.5)

    # 3. Încercați registrele MPPT (40266+) - DOAR pentru Invertoare
    if result.get("device_type") == "inverter":
        # Adresa de pornire: 40266, care este offset 265 (40266 - 40001)
        MPPT_START_ADDR = 265
        MPPT_COUNT = 50 
        
        print(f"Reading MPPT registers (40266+) from offset {MPPT_START_ADDR}...")
        try:
            # CORECTIE CRITICĂ: address=265 (pentru 40266)
            response = client.read_holding_registers(address=MPPT_START_ADDR, count=MPPT_COUNT, slave=device_id)
            if response.isError():
                result["errors"].append(f"MPPT read failed: {response}")
                print(f"  MPPT: Not available or error")
            else:
                regs = response.registers
                result["raw_blocks"][f"40266-40{40265 + MPPT_COUNT}"] = regs

                mppt_id = regs[0]
                result["registers"]["40266"] = {"name": "MPPT_ID", "value": mppt_id, "description": "MPPT Model ID"}

                if mppt_id == 160:
                    print(f"  MPPT Model 160 found!")
                    # Logica de parsare MPPT similară cu cea Inverter (folosind diferența de adresă)
                    mppt_regs = [
                        (40267, "MPPT_L", "MPPT Length"), (40268, "MPPT_DCA_SF", "DC Current SF"),
                        (40269, "MPPT_DCV_SF", "DC Voltage SF"), (40270, "MPPT_DCW_SF", "DC Power SF"),
                        (40271, "MPPT_DCWH_SF", "DC Energy SF"), (40272, "MPPT_N", "Num Modules"),
                        (40273, "MPPT_TmsPer", "Timestamp Period"),
                    ]
                    for addr, name, desc in mppt_regs:
                        idx = addr - 40266
                        if idx < len(regs):
                            val = regs[idx]
                            if "_SF" in name:
                                val = decode_int16(val)
                            result["registers"][str(addr)] = {"name": name, "value": val, "description": desc}
                            
                    # ATENȚIE: M1_DCWH (40282-40283) este 32-bit (regs[16:18]) și necesită decode_uint32, 
                    # dar scanerul tău inițial a omis parsarea completă a modelelor MPPT.
                else:
                    print(f"  MPPT ID: {mppt_id} (not Model 160)")

        except Exception as e:
            result["errors"].append(f"MPPT exception: {str(e)}")
            print(f"  MPPT EXCEPTION: {e}")

        time.sleep(0.5)

        # 4. Încercați registrele de Stocare (Model 124) - DOAR pentru Invertoare
        # Adresa de pornire: 40341, care este offset 340 (40341 - 40001)
        STORAGE_START_ADDR = 340
        STORAGE_COUNT = 28 # Acoperă până la 40368
        
        print(f"Reading Storage (Model 124) registers (40341+) from offset {STORAGE_START_ADDR}...")
        try:
            # CORECTIE CRITICĂ: address=340 (pentru 40341)
            response = client.read_holding_registers(address=STORAGE_START_ADDR, count=STORAGE_COUNT, slave=device_id)
            if response.isError():
                result["errors"].append(f"Storage read failed: {response}")
                print(f"  Storage: Not available or error")
            else:
                regs = response.registers
                result["raw_blocks"][f"40341-40{40340 + STORAGE_COUNT}"] = regs

                storage_id = regs[0]
                result["registers"]["40341"] = {"name": "Storage_ID", "value": storage_id, "description": "Storage Model ID"}

                if storage_id == 124:
                    print(f"  Storage Model 124 found! (Battery support detected)")
                    result["has_storage"] = True
                    # Logica de parsare Storage similară
                    storage_regs = [
                        (40342, "Storage_L", "Storage Length"), (40343, "WChaMax", "Max Charge Power"),
                        # ... și celelalte registre ...
                        (40366, "InOutWRte_SF", "Rate SF"),
                    ]
                    
                    # Logica de parsare a registrelor Storage (40342-40366) este corectă
                    # presupunând că regs[0] este 40341.
                    for addr, name, desc in storage_regs:
                        idx = addr - 40341 # Indexul corect în lista regs
                        if idx < len(regs):
                            val = regs[idx]
                            if "_SF" in name:
                                val = decode_int16(val)
                            result["registers"][str(addr)] = {"name": name, "value": val, "description": desc}

                    # Decodare status și SoC (folosind indexuri corecte din lista regs)
                    cha_st = regs[11] if len(regs) > 11 else None
                    cha_st_names = {1: "OFF", 2: "EMPTY", 3: "DISCHARGING", 4: "CHARGING", 5: "FULL", 6: "HOLDING", 7: "TESTING"}
                    if cha_st in cha_st_names:
                        print(f"    Charge Status: {cha_st_names[cha_st]}")

                    cha_state_sf = decode_int16(regs[22]) if len(regs) > 22 else -2
                    cha_state = regs[8] if len(regs) > 8 else None
                    if cha_state is not None and cha_state_sf is not None and cha_state_sf != 0x8000:
                        soc = cha_state * (10 ** cha_state_sf)
                        print(f"    State of Charge: {soc}%")
                else:
                    print(f"  Storage ID: {storage_id} (not Model 124 - no battery)")
                    result["has_storage"] = False

        except Exception as e:
            result["errors"].append(f"Storage exception: {str(e)}")
            print(f"  Storage EXCEPTION: {e}")

    return result


def main():
    print("="*60)
    print("Fronius Modbus Register Scanner")
    print(f"Host: {MODBUS_HOST}:{MODBUS_PORT}")
    print(f"Devices to scan: {DEVICE_IDS}")
    print("="*60)

    all_results = {}

    for device_id in DEVICE_IDS:
        # Create fresh connection for each device
        client = ModbusTcpClient(
            host=MODBUS_HOST,
            port=MODBUS_PORT,
            timeout=TIMEOUT
        )

        try:
            if not client.connect():
                print(f"\nFailed to connect for device {device_id}")
                all_results[f"device_{device_id}"] = {"error": "Connection failed"}
                continue

            is_meter = device_id >= 200
            result = scan_device(client, device_id, is_meter)
            all_results[f"device_{device_id}"] = result

        except Exception as e:
            print(f"\nError scanning device {device_id}: {e}")
            all_results[f"device_{device_id}"] = {"error": str(e)}
        finally:
            client.close()
            time.sleep(1)  # Wait between devices

    # Save results
    output_file = "register_scan_results.json"
    with open(output_file, 'w') as f:
        # Folosiți default=str pentru a serializa obiecte complexe precum 'response' în caz de erori
        json.dump(all_results, f, indent=2, default=str) 

    print(f"\n{'='*60}")
    print(f"Results saved to: {output_file}")
    print("="*60)

    # Summary
    print("\nSummary:")
    for device_key, data in all_results.items():
        if "error" in data and isinstance(data["error"], str):
            print(f"  {device_key}: ERROR - {data['error']}")
        elif "errors" in data and data["errors"]:
            print(f"  {device_key}: Partial ({len(data.get('registers', {}))} registers, {len(data['errors'])} errors)")
        else:
            dev_type = data.get("device_type", "unknown")
            reg_count = len(data.get("registers", {}))
            print(f"  {device_key}: {dev_type} - {reg_count} registers")


if __name__ == "__main__":
    main()
