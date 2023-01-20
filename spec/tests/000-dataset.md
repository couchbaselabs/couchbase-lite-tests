# Dataset

## 1. travel-sample

### CBL Dataset

| Collections         | #Docs       | #Size (bytes) |
| :------------------ | ----------- | ------------- |
| inventory.airline   | 187         | 34.8K         |
| inventory.route     | 24000       | 12.7M         |
| inventory.airport   | 0           | 0             |
| inventory.landmark  | 0           | 0             |
| inventory.hotel     | 458         | TBD           |

### SG Dataset

| Collections         | #Docs       | #Size (bytes) |
| :------------------ | ----------- | ------------- |
| inventory.airline   | 0           | 0             |
| inventory.route     | 0           | 0             |
| inventory.airport   | 1960        | 455K          |
| inventory.landmark  | 4490        | 2.86M         |
| inventory.hotel     | 459         | TBD           |

Note: the documents in the `inventory.hotel` collections of CBL and SG will have different document IDs.

### Sample Docs

#### inventory.airline

```JSON
{
    "_id": "airline_10",
    "id": 10,
    "type": "airline",
    "name": "40-Mile Air",
    "iata": "Q5",
    "icao": "MLA",
    "callsign": "MILE-AIR",
    "country": "United States"
}
```

#### inventory.route

```JSON
{
    "_id": "route_10009",
    "id": 10009,
    "type": "route",
    "airline": "AF",
    "airlineid": "airline_137",
    "sourceairport": "TUN",
    "destinationairport": "CDG",
    "stops": 0,
    "equipment": "321 319 320",
    "schedule": [{
        "day": 0,
        "utc": "13:22:00",
        "flight": "AF665"
    }, {
        "day": 1,
        "utc": "16:10:00",
        "flight": "AF232"
    }, {
        "day": 2,
        "utc": "07:49:00",
        "flight": "AF335"
        }],
    "distance": 1487.9098005221067
}
```

#### inventory.airport

```JSON
{
    "_id": "airport_1254",
    "id": 1254,
    "type": "airport",
    "airportname": "Calais Dunkerque",
    "city": "Calais",
    "country": "France",
    "faa": "CQF",
    "icao": "LFAC",
    "tz": "Europe/Paris",
    "geo": {
        "lat": 50.962097,
        "lon": 1.954764,
        "alt": 12
    }
}
```

#### inventory.landmark

``` JSON
{
    "_id": "landmark_10020",
    "id": 10020,
    "type": "landmark",
    "title": "Gillingham (Kent)",
    "name": "Hollywood Bowl",
    "alt": null,
    "address": "4 High Street, ME7 1BB",
    "directions": null,
    "phone": null,
    "tollfree": null,
    "email": null,
    "url": "http://www.thehollywoodbowl.co.uk",
    "hours": null,
    "image": null,
    "price": null,
    "content": "A newly extended lively restaurant",
    "geo": {
        "lat": 51.38937,
        "lon": 0.5427,
        "accuracy": "RANGE_INTERPOLATED"
        },
    "activity": "eat",
    "country": "United Kingdom",
    "city": "Gillingham",
    "state": null
}
```

#### inventory.hotel

```JSON
{
    "_id": "hotel_10026"
    "id": 10026,
    "type": "hotel",
    "title": "Gillingham (Kent)",
    "name": "The Balmoral Guesthouse",
    "address": "57-59 Balmoral Road, ME7 4NT",
    "directions": null,
    "phone": "+44 1634 853 68",
    "tollfree": null,
    "email": null,
    "fax": null,
    "url": "http://www.thebalmoral-guesthouse.co.uk",
    "checkin": null,
    "checkout": null,
    "price": "Single room £32 per night",
    "geo": {
        "lat": 51.38624,
        "lon": 0.55078,
        "accuracy": "RANGE_INTERPOLATED"
    },
    "country": "United Kingdom",
    "city": "Gillingham",
    "state": null,
    "reviews": [],
    "public_likes": [],
    "vacancy": false,
    "description": "A recently modernised guesthouse.",
    "alias": null,
    "pets_ok": true,
    "free_breakfast": true,
    "free_internet": true,
    "free_parking": false
}
```

## 2. names-100

The 100 name documents in the default collection.

### CBL Dataset

| Collections         | #Docs       | #Size (bytes) |
| :------------------ | ----------- | ------------- |
| _default._default   | 100         | TBD           |

### SG Dataset

| Collections         | #Docs       | #Size (bytes) |
| :------------------ | ----------- | ------------- |
| _default._default   | 100         | TBD           |

Note: The documents populated to CBL and SG will have different document IDs.

### Sample Docs

```JSON
{
    "_id" : "name_1",
    "name": {
        "first": "Lue",
        "last": "Laserna"
    },
    "gender": "female",
    "birthday": "1983-09-18",
    "contact": {
        "address": {
            "street": "19 Deer Loop",
            "zip": "90732",
            "city": "San Pedro",
            "state": "CA"
        },
        "email": [
            "lue.laserna@nosql-matters.org",
            "laserna@nosql-matters.org"
        ],
        "region": "310",
        "phone": [
            "310-8268551",
            "310-7618427"
        ]
    },
    "likes": ["chatting"],
    "memberSince": "2011-05-05"
}
```

## 3. default_empty (SG only)

The SG only dataset that contains only an empty default collection.

### SG Dataset

| Collections         | #Docs       | #Size (bytes) |
| :------------------ | ----------- | ------------- |
| _default._default   | 0           | 0             |
