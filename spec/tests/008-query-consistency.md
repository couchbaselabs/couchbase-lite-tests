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