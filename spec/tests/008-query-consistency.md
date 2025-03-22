# Test Cases

## Notes

Unlike other test suites, this one operates on a set of data that is never written to.  Thus,
the suite can setup the server side data once in a setup method and then run all tests on it
without tearing down and resetting.

Most, if not all, of these tests will follow the same basic structure:

- Run query on test server
- Run query on Couchbase server
- Compare results

Each section specifies, before the steps, any variables used in the steps themselves.  If it is
in array syntax, it means that the test should be run multiple times, once for each variation
(i.e. pytest.parametrize)

## #1 test_query_docids

### Description

Verify consistency using a query that selects meta().id

### Steps

`query` = SELECT meta().id FROM travel.airlines WHERE meta().id NOT LIKE "_sync%" ORDER BY id

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Sort results by `result.id`
4. Check that the results are equal
   
## #2 test_any_operator

### Description

Verify consistency using a query that uses the `ANY` operator

### Steps

`query` = SELECT meta().id FROM travel.routes WHERE ANY departure IN schedule SATISFIES departure.utc > "23:41:00" END

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Sort results by `result.id`
4. Check that the results are equal

## #3 test_select_star

### Description

Verify consistency using a query that contains a `SELECT *`

### Steps

`doc_id` = [airline_10, doc_id_does_not_exist]<br />
`query` = SELECT * FROM travel.airlines WHERE meta().id = `doc_id`

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal

## #4 test_limit_offset

### Description

Verify that LIMIT functions as intended (does not return more than requested)

### Steps

`limit` = [5, -5]<br />
`offset` = [5, -5]<br />
`query` = SELECT meta().id FROM travel.airlines WHERE meta().id NOT LIKE "_sync%" LIMIT `limit` OFFSET `offset`

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are of length 5, or 0, depending on if 5 or -5 was passed

## #5 test_query_where_and_or

### Description

Verify consistency using a query that uses both `AND` and `OR`

### Steps

`query` = SELECT meta().id FROM travel.hotels WHERE (country = "United States" OR country = "France") AND vacancy = true

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Sort results by `result.id`
4. Check that the results are equal

## #6 test_multiple_selects

### Description

Verify consistency using a query that has multiple select clauses.

### Steps

`query` = SELECT name, meta().id FROM travel.hotels WHERE country = "France"

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Sort results by `result.id`
4. Check that the results are equal

## #7 test_query_pattern_like

### Description

Verify consistency using a query that makes use of the `LIKE` keyword

### Steps

`like_val` = [Royal Engineers Museum, Royal engineers museum, eng%e%, Eng%e%, %eng____r%, %Eng____r%]<br />
`query` = SELECT meta().id, country, name FROM travel.landmarks WHERE name LIKE "`like_val`"

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Sort results by `result.id`
4. Check that the results are equal

## #8 test_query_pattern_regex

### Description

Verify consistency using a query that makes use of the `regexp_contains` function

### Steps

`regex` = [\bEng.*e\b, \beng.*e\b]<br />
`query` = SELECT meta().id, country, name FROM travel.landmarks t WHERE REGEXP_CONTAINS(t.name, "{regex}")

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Sort results by `result.id`
4. Check that the results are equal

## #9 test_query_is_not_valued

### Description

Verify consistency using a query that makes use of `IS NULL OR IS MISSING`

### Steps

`query` = SELECT meta().id, name FROM travel.hotels WHERE meta().id NOT LIKE "_sync%" and (name IS NULL OR name IS MISSING) ORDER BY name ASC LIMIT 100

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal

## #10 test_query_ordering

### Description

Verify consistent ordering as governed by the ORDER BY clause.  Note the WHERE clause
is kept here to avoid picking up _sync docs.

### Steps

`query` = SELECT meta().id, title FROM travel.hotels WHERE type = "hotel" ORDER BY name ASC

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal

## #11 test_query_substring

### Description

Verify consistency using a query that makes use of the `substring` function

### Steps

`query` = SELECT meta().id, email, UPPER(name) from travel.landmarks t where CONTAINS(t.email, "gmail.com")

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal

## #12 test_query_join

### Description

Verify consistency using a query that makes use of the `JOIN` keyword.  The queries are
slightly different because lite does not support the `ON KEYS` clause.

### Steps

`query` = SELECT DISTINCT airlines.name, airlines.callsign,<br />
          routes.destinationairport, routes.stops, routes.airline<br />
          FROM travel.routes as routes<br />
           JOIN travel.airlines AS airlines<br />
           ON routes.airlineid = meta(airlines).id<br />
          WHERE routes.sourceairport = "SFO"<br />
          ORDER BY meta(routes).id<br />
          LIMIT 2<br />

`server_query` = SELECT DISTINCT airlines.name, airlines.callsign, <br />
                 routes.destinationairport, routes.stops, routes.airline<br />
                 FROM travel.travel.routes as routes<br />
                  JOIN travel.travel.airlines AS airlines<br />
                  ON KEYS routes.airlineid<br />
                 WHERE routes.sourceairport = "SFO"<br />
                 ORDER BY meta(routes).id<br />
                 LIMIT 2<br />

1. Run `query` on test server
2. Run `server_query` on Couchbase Server
3. Check that the results are equal

## #13 test_query_inner_join

### Description

Verify consistency using a query that makes use of the `INNER JOIN` keyword. 

### Steps

`query` =   SELECT routes.airline, routes.sourceairport, airports.country<br />
            FROM travel.routes as routes<br />
             INNER JOIN travel.airports AS airports<br />
             ON airports.icao = routes.destinationairport<br />
            WHERE airports.country = "United States"<br />
             AND routes.stops = 0
            

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal

## #14 test_query_left_join

### Description

Verify consistency using a query that makes use of the `LEFT JOIN` and `LEFT OUTER JOIN` keywords.  
The queries are slightly different because lite does not support the `ON KEYS` clause.  Furthermore,
Lite doesn't support `LEFT OUTER JOIN` so it simply uses `LEFT JOIN` for both.

### Steps

`server_join_type` = [LEFT JOIN, LEFT OUTER JOIN]

`query` =   SELECT airlines, routes<br />
            FROM travel.routes AS routes<br />
             LEFT JOIN travel.airlines AS airlines<br />
             ON meta(airlines).id = routes.airlineid<br />
            ORDER BY meta(routes).id<br />
            LIMIT 10<br />

`server_query` = SELECT airlines, routes<br />
            FROM travel.travel.routes<br />
             `{server_join_type}` travel.travel.airlines<br />
             ON KEYS routes.airlineid<br />
            WHERE meta(routes).id NOT LIKE "_sync%"<br />
            ORDER BY meta(routes).id<br />
            LIMIT 10<br />
            

1. Run `query` on test server
2. Run `server_query` on Couchbase Server
3. Check that the results are equal

## #15 test_equality

### Description

Verify consistency using a query that makes use of the `=` and `!=` operators

### Steps

`operation` = [=, !=]

`query` = SELECT meta().id, name FROM travel.airports WHERE country `{operation}` "France" ORDER BY meta().id ASC

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal

## #16 test_comparison

### Description

Verify consistency using a query that makes use of the `>`, `>=`, `<` and `<=` operators

### Steps

`operation` = [>, >=, <, <=]

`query` = SELECT meta().id FROM travel.airports WHERE geo.alt `{operation}` 1000 ORDER BY meta().id ASC

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal

## #17 test_in

### Description

Verify consistency using a query that makes use of the `IN` keyword

### Steps

`query` = SELECT meta().id FROM travel.airports WHERE (country IN ["United States", "France"]) ORDER BY meta().id ASC

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal

## #18 test_between

### Description

Verify consistency using a query that makes use of the `BETWEEN` and `NOT BETWEEN` keywords

### Steps

`keyword` = [BETWEEN, NOT BETWEEN]

`query` = SELECT meta().id FROM travel.airports WHERE geo.alt `{keyword}` 100 and 200 ORDER BY meta().id ASC

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal

## #19 test_same

### Description

Verify consistency using a query that makes use of the `IS` and `IS NOT` keywords

### Steps

`keyword` = [IS, IS NOT]

`query` = SELECT meta().id FROM travel.airports WHERE iata `{keyword}` null ORDER BY meta().id ASC

1. Run `query` on test server
2. Run `query` on Couchbase Server
3. Check that the results are equal