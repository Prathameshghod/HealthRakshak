from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import tempfile
from typing import Dict, List, Set, Tuple

app = Flask(__name__)
CORS(app)

SECTION_START = '['

def _is_section_header(line: str) -> bool:
    return line.strip().startswith(SECTION_START) and line.strip().endswith(']')

def _read_inp_sections(file_path: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {}
    current: str = ''
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith(';'):
                continue
            if _is_section_header(line):
                current = line.strip('[]').upper()
                sections.setdefault(current, [])
                continue
            if current:
                sections[current].append(line)
    return sections

def get_skip_nodes_from_elevation(file_path: str, elevation_threshold: float) -> Set[str]:
    sections = _read_inp_sections(file_path)
    skip_nodes: Set[str] = set()
    for line in sections.get('JUNCTIONS', []):
        if line.startswith(';'):
            continue
        parts = line.split()
        if len(parts) >= 2:
            try:
                elevation = float(parts[1])
                if elevation > elevation_threshold:
                    skip_nodes.add(parts[0])
            except ValueError:
                continue
    return skip_nodes

def create_graph_from_inp(file_path: str, elevation_threshold: float = 100.0) -> Tuple[Dict[str, List[Tuple[str, float]]], Dict[str, float]]:
    sections = _read_inp_sections(file_path)
    skip_nodes = get_skip_nodes_from_elevation(file_path, elevation_threshold)
    node_neighbors: Dict[str, List[Tuple[str, float]]] = {}

    for line in sections.get('PIPES', []):
        parts = line.split()
        if len(parts) >= 3:
            n1, n2 = parts[1], parts[2]
            if n1 in skip_nodes or n2 in skip_nodes:
                continue
            node_neighbors.setdefault(n1, []).append((n2, 1.0))
            node_neighbors.setdefault(n2, []).append((n1, 1.0))

    return node_neighbors, {}

# Function to find the nearest neighbor for each node
def find_nearest_neighbors(graph: Dict[str, List[Tuple[str, float]]]) -> Dict[str, str]:
    nearest = {}
    for node_id, edges in graph.items():
        if edges:
            closest = min(edges, key=lambda x: x[1])[0]
            nearest[node_id] = closest
    return nearest

# Function to identify initial sensor nodes
def identify_initial_sensor_nodes(nearest: Dict[str, str]) -> Set[str]:
    counts = {}
    for n in nearest.values():
        counts[n] = counts.get(n, 0) + 1

    sensors: Set[str] = set()
    for node, count in counts.items():
        if count > 1:
            sensors.add(node)
    return sensors

# Function to identify left-out nodes
def identify_left_out_nodes(nearest: Dict[str, str], sensors: Set[str]) -> Set[str]:
    left_out_nodes: Set[str] = set()
    for node, neighbor in nearest.items():
        if neighbor not in sensors:
            left_out_nodes.add(node)
    return left_out_nodes

# Function to remove redundant sensor nodes
def remove_redundant_sensors(graph: Dict[str, List[Tuple[str, float]]], sensors: Set[str]) -> Set[str]:
    redundant: Set[str] = set()
    for s in sensors:
        is_redundant = True
        for neighbor, _ in graph[s]:
            if neighbor not in sensors:
                is_redundant = False
                break
        if is_redundant:
            redundant.add(s)
    
    sensors.difference_update(redundant)
    return sensors

# Function to map non-sensor nodes to sensor nodes
def map_to_sensors(nearest: Dict[str, str], sensors: Set[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for node, neighbor in nearest.items():
        if node not in sensors:
            mapping[node] = nearest[node]
    return mapping

def identify_sensor_nodes(file_path: str) -> Set[str]:
    node_neighbors, _ = create_graph_from_inp(file_path)

    nearest_neighbors = find_nearest_neighbors(node_neighbors)
    initial_sensors = identify_initial_sensor_nodes(nearest_neighbors)
    left_out_nodes = identify_left_out_nodes(nearest_neighbors, initial_sensors)
    sensors = initial_sensors.union(left_out_nodes)
    sensors = remove_redundant_sensors(node_neighbors, sensors)
    return sensors

def main(file_path: str):
    sensors = identify_sensor_nodes(file_path)
    node_neighbors, _ = create_graph_from_inp(file_path)

    nearest_neighbors = find_nearest_neighbors(node_neighbors)
    sensors = remove_redundant_sensors(node_neighbors, sensors)
    mapping = map_to_sensors(nearest_neighbors, sensors)

    print("Sensor Nodes:")
    print(' '.join(map(str, sensors)))

    print("Mapping of Non-Sensor Nodes to Sensor Nodes:")
    for node, sensor in mapping.items():
        print(f"Node {node} is covered by Sensor Node {sensor}")

@app.route('/sensor-allocation', methods=['POST'])
def sensor_allocation():
    # Check if the request contains the file
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']

    # Check if a file was actually uploaded
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    # Save the uploaded file to a temporary file
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    file.save(temp_file.name)
    temp_file.close()  # Close the file before attempting to delete it

    try:
        sensors = identify_sensor_nodes(temp_file.name)
        node_neighbors, _ = create_graph_from_inp(temp_file.name)

        nearest_neighbors = find_nearest_neighbors(node_neighbors)
        sensors = remove_redundant_sensors(node_neighbors, sensors)
        mapping = map_to_sensors(nearest_neighbors, sensors)

        return jsonify({
            'sensor_nodes': list(sensors),
            'mapping': mapping
        })
    finally:
        os.unlink(temp_file.name)  # Delete the temporary file

if __name__ == '__main__':
    app.run(debug=True, port=8080)