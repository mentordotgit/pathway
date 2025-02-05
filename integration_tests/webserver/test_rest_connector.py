# Copyright © 2024 Pathway

import multiprocessing
import pathlib
import threading
import time

import pytest
import requests

import pathway as pw
from pathway.tests.utils import (
    CsvLinesNumberChecker,
    expect_csv_checker,
    wait_result_with_checker,
)


def _test_server_basic(tmp_path: pathlib.Path, port: int, port_is_str: bool = False):
    if port_is_str:
        port = str(port)
    output_path = tmp_path / "output.csv"

    class InputSchema(pw.Schema):
        query: str
        user: str

    def logic(queries: pw.Table) -> pw.Table:
        return queries.select(
            query_id=queries.id, result=pw.apply(lambda x: x.upper(), pw.this.query)
        )

    def target():
        time.sleep(5)
        r = requests.post(
            f"http://127.0.0.1:{port}",
            json={"query": "one", "user": "sergey"},
        )
        r.raise_for_status()
        assert r.text == '"ONE"', r.text
        r = requests.post(
            f"http://127.0.0.1:{port}",
            json={"query": "two", "user": "sergey"},
        )
        r.raise_for_status()
        assert r.text == '"TWO"', r.text

    queries, response_writer = pw.io.http.rest_connector(
        host="127.0.0.1", port=port, schema=InputSchema, delete_completed_queries=True
    )
    responses = logic(queries)
    response_writer(responses)
    pw.io.csv.write(queries, output_path)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    wait_result_with_checker(CsvLinesNumberChecker(output_path, 4), 30)


def test_server(tmp_path: pathlib.Path, port: int):
    _test_server_basic(tmp_path, port)


def test_server_str_port_compatibility(tmp_path: pathlib.Path, port: int):
    _test_server_basic(tmp_path, port, port_is_str=True)


def test_server_customization(tmp_path: pathlib.Path, port: int):
    output_path = tmp_path / "output.csv"

    class InputSchema(pw.Schema):
        query: str
        user: str

    def logic(queries: pw.Table) -> pw.Table:
        return queries.select(
            query_id=queries.id, result=pw.apply(lambda x: x.upper(), pw.this.query)
        )

    def target():
        time.sleep(5)
        requests.post(
            f"http://127.0.0.1:{port}/endpoint?user=sergey",
            json={"query": "one"},
        ).raise_for_status()
        requests.post(
            f"http://127.0.0.1:{port}/endpoint?user=sergey",
            json={"query": "two"},
        ).raise_for_status()

    queries, response_writer = pw.io.http.rest_connector(
        host="127.0.0.1",
        port=port,
        schema=InputSchema,
        route="/endpoint",
        delete_completed_queries=True,
    )
    responses = logic(queries)
    response_writer(responses)
    pw.io.csv.write(queries, output_path)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    wait_result_with_checker(CsvLinesNumberChecker(output_path, 4), 30)


def test_server_schema_customization(tmp_path: pathlib.Path, port: int):
    output_path = tmp_path / "output.csv"

    class InputSchema(pw.Schema):
        query: str
        user: str = pw.column_definition(default_value="manul")

    def logic(queries: pw.Table) -> pw.Table:
        return queries.select(
            query_id=queries.id, result=pw.apply(lambda x: x.upper(), pw.this.query)
        )

    def target():
        time.sleep(5)
        requests.post(
            f"http://127.0.0.1:{port}/",
            json={"query": "one"},
        ).raise_for_status()
        requests.post(
            f"http://127.0.0.1:{port}/",
            json={"query": "two"},
        ).raise_for_status()

    queries, response_writer = pw.io.http.rest_connector(
        host="127.0.0.1", port=port, schema=InputSchema, delete_completed_queries=True
    )
    responses = logic(queries)
    response_writer(responses)
    pw.io.csv.write(queries, output_path)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    wait_result_with_checker(CsvLinesNumberChecker(output_path, 4), 30)


def test_server_keep_queries(tmp_path: pathlib.Path, port: int):
    output_path = tmp_path / "output.csv"

    class InputSchema(pw.Schema):
        k: int
        v: int

    def target():
        time.sleep(5)
        requests.post(
            f"http://127.0.0.1:{port}/",
            json={"k": 1, "v": 1},
        ).raise_for_status()
        requests.post(
            f"http://127.0.0.1:{port}/",
            json={"k": 1, "v": 2},
        ).raise_for_status()

    queries, response_writer = pw.io.http.rest_connector(
        host="127.0.0.1", port=port, schema=InputSchema, delete_completed_queries=False
    )
    response_writer(queries.select(query_id=queries.id, result=pw.this.v))

    sum = queries.groupby(pw.this.k).reduce(
        key=pw.this.k, sum=pw.reducers.sum(pw.this.v)
    )

    pw.io.csv.write(sum, output_path)

    t = threading.Thread(target=target, daemon=True)
    t.start()

    wait_result_with_checker(
        expect_csv_checker(
            """
            key | sum    | diff
            1   | 1      | 1
            1   | 1      | -1
            1   | 3      | 1
            """,
            output_path,
            usecols=["sum", "diff"],
            index_col=["key"],
        ),
        10,
    )


def test_server_fail_on_duplicate_port(tmp_path: pathlib.Path, port: int):
    output_path = tmp_path / "output.csv"

    class InputSchema(pw.Schema):
        k: int
        v: int

    queries, response_writer = pw.io.http.rest_connector(
        host="127.0.0.1", port=port, schema=InputSchema, delete_completed_queries=False
    )
    response_writer(queries.select(query_id=queries.id, result=pw.this.v))

    queries_dup, response_writer_dup = pw.io.http.rest_connector(
        host="127.0.0.1", port=port, schema=InputSchema, delete_completed_queries=False
    )
    response_writer_dup(queries_dup.select(query_id=queries_dup.id, result=pw.this.v))

    sum = queries.groupby(pw.this.k).reduce(
        key=pw.this.k, sum=pw.reducers.sum(pw.this.v)
    )
    sum_dup = queries_dup.groupby(pw.this.k).reduce(
        key=pw.this.k, sum=pw.reducers.sum(pw.this.v)
    )

    pw.io.csv.write(sum, output_path)
    pw.io.csv.write(sum_dup, output_path)

    with pytest.raises(RuntimeError, match="error while attempting to bind on address"):
        pw.run()


def _test_server_two_endpoints(tmp_path: pathlib.Path, port: int, with_cors: bool):
    output_path = tmp_path / "output.csv"

    class InputSchema(pw.Schema):
        query: str
        user: str

    def uppercase_logic(queries: pw.Table) -> pw.Table:
        return queries.select(
            query_id=queries.id, result=pw.apply(lambda x: x.upper(), pw.this.query)
        )

    def duplicate_logic(queries: pw.Table) -> pw.Table:
        return queries.select(
            query_id=queries.id, result=pw.apply(lambda x: x + x, pw.this.query)
        )

    def target():
        time.sleep(5)
        r = requests.post(
            f"http://127.0.0.1:{port}/duplicate",
            json={"query": "one", "user": "sergey"},
        )
        r.raise_for_status()
        assert r.text == '"oneone"', r.text
        r = requests.get(f"http://127.0.0.1:{port}/duplicate?query=two&user=sergey")
        r.raise_for_status()
        assert r.text == '"twotwo"', r.text
        r = requests.post(
            f"http://127.0.0.1:{port}/uppercase",
            json={"query": "one", "user": "sergey"},
        )
        r.raise_for_status()
        assert r.text == '"ONE"', r.text
        r = requests.get(f"http://127.0.0.1:{port}/uppercase?query=two&user=sergey")
        r.raise_for_status()
        assert r.text == '"TWO"', r.text

    webserver = pw.io.http.PathwayWebserver(
        host="127.0.0.1",
        port=port,
        with_cors=with_cors,
    )

    uppercase_queries, uppercase_response_writer = pw.io.http.rest_connector(
        webserver=webserver,
        schema=InputSchema,
        route="/uppercase",
        methods=(
            "GET",
            "POST",
        ),
        delete_completed_queries=True,
    )
    uppercase_responses = uppercase_logic(uppercase_queries)
    uppercase_response_writer(uppercase_responses)

    duplicate_queries, duplicate_response_writer = pw.io.http.rest_connector(
        webserver=webserver,
        schema=InputSchema,
        route="/duplicate",
        methods=(
            "GET",
            "POST",
        ),
        delete_completed_queries=True,
    )
    duplicate_responses = duplicate_logic(duplicate_queries)
    duplicate_response_writer(duplicate_responses)

    pw.universes.promise_are_pairwise_disjoint(uppercase_queries, duplicate_queries)
    all_queries = uppercase_queries.concat(duplicate_queries)

    pw.io.csv.write(all_queries, output_path)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    wait_result_with_checker(CsvLinesNumberChecker(output_path, 8), 30)


def test_server_two_endpoints_without_cors(tmp_path: pathlib.Path, port: int):
    _test_server_two_endpoints(tmp_path, port, with_cors=False)


def test_server_two_endpoints_with_cors(tmp_path: pathlib.Path, port: int):
    _test_server_two_endpoints(tmp_path, port, with_cors=True)


def test_server_schema_generation_via_endpoint(port: int):
    class InputSchema(pw.Schema):
        query: str
        user: str

    def uppercase_logic(queries: pw.Table) -> pw.Table:
        return queries.select(
            query_id=queries.id, result=pw.apply(lambda x: x.upper(), pw.this.query)
        )

    webserver = pw.io.http.PathwayWebserver(host="127.0.0.1", port=port)
    uppercase_queries, uppercase_response_writer = pw.io.http.rest_connector(
        webserver=webserver,
        schema=InputSchema,
        route="/uppercase",
        delete_completed_queries=True,
    )
    uppercase_responses = uppercase_logic(uppercase_queries)
    uppercase_response_writer(uppercase_responses)

    pw_run_process = multiprocessing.Process(target=pw.run)
    pw_run_process.start()

    succeeded = False
    for _ in range(10):
        try:
            response = requests.get(
                f"http://127.0.0.1:{port}/_schema?format=json", timeout=1
            )
            response.raise_for_status()
        except Exception:
            time.sleep(0.5)
            continue

        schema = response.json()
        assert schema["paths"].keys() == {"/uppercase"}
        succeeded = True
        break

    pw_run_process.terminate()
    pw_run_process.join()
    assert succeeded


def test_server_parameter_cast(tmp_path: pathlib.Path, port: int):
    output_path = tmp_path / "output.csv"

    class InputSchema(pw.Schema):
        number: int

    def double_logic(queries: pw.Table) -> pw.Table:
        return queries.select(
            query_id=queries.id, result=pw.apply(lambda x: x + x, pw.this.number)
        )

    def target():
        time.sleep(5)
        r = requests.post(
            f"http://127.0.0.1:{port}/double",
            json={"number": 5},
        )
        r.raise_for_status()
        assert r.text == "10", r.text
        r = requests.get(f"http://127.0.0.1:{port}/double?number=7")
        r.raise_for_status()
        assert r.text == "14", r.text

    webserver = pw.io.http.PathwayWebserver(host="127.0.0.1", port=port)

    double_queries, double_response_writer = pw.io.http.rest_connector(
        webserver=webserver,
        schema=InputSchema,
        route="/double",
        methods=(
            "GET",
            "POST",
        ),
        delete_completed_queries=True,
    )
    double_responses = double_logic(double_queries)
    double_response_writer(double_responses)

    pw.io.csv.write(double_queries, output_path)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    wait_result_with_checker(CsvLinesNumberChecker(output_path, 4), 30)


def test_server_parameter_cast_json(tmp_path: pathlib.Path, port: int):
    output_path = tmp_path / "output.csv"

    class InputSchema(pw.Schema):
        data: pw.Json

    def echo_logic(queries: pw.Table) -> pw.Table:
        return queries.select(query_id=queries.id, result=pw.this.data)

    def target():
        time.sleep(5)
        r = requests.post(f"http://127.0.0.1:{port}/echo", json={"data": {"a": 1}})
        r.raise_for_status()
        assert r.text == '{"a": 1}', r.text

    webserver = pw.io.http.PathwayWebserver(host="127.0.0.1", port=port)

    echo_queries, echo_response_writer = pw.io.http.rest_connector(
        webserver=webserver,
        schema=InputSchema,
        route="/echo",
        delete_completed_queries=True,
    )
    echo_queries = echo_logic(echo_queries)
    echo_response_writer(echo_queries)

    pw.io.csv.write(echo_queries, output_path)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    wait_result_with_checker(CsvLinesNumberChecker(output_path, 2), 30)
