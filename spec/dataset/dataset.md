# Dataset

## 1. travel

### CBL

| Collections         | #Docs       | Doc ID              |
| :------------------ | ----------- |---------------------|
| travel.airlines     | 150         | airline_1 ... 150   |
| travel.routes       | 3000        | route_1 ... 3000    |
| travel.airports     | 0           |                     |
| travel.landmarks    | 0           |                     |
| travel.hotels       | 350         | hotel_1 ... 350     |

### SG

| Collections         | #Docs       | Doc ID              |
| :------------------ | ----------- |---------------------|
| travel.airlines     | 0           |                     | 
| travel.routes       | 0           |                     |
| travel.airports     | 300         | airport_1 ... 300   |
| travel.landmarks    | 900         | landmark_1 ... 900  |
| travel.hotels       | 350         | hotel_351 ... 700   |

Note: 
* Each document has `scope` and `collection` key.
* First 20 documents (hotel_1 - 20) in CBL's `travel.hotels` has "image" key which contains a unique blob.
* Each doucment in this dataset has "channels" property which contain a country value ("United States", "United Kingdom" or "France")

### SG Config

 | Config      | Value       |
 | ----------- | ----------- |
 | Database    | travel      |
 | Port        | 4984 / 4985 |
 | Collections | travel.airlines, travel.routes, travel.airports, travel.landmarks, travel.hotels |

#### Sync Function

```js
function (doc, oldDoc, meta) {
  if (doc._deleted) {
    channel(oldDoc.channels)
  } else {
    channel(doc.channels)
  }
}
```
Note: Same sync function for all collections

#### Users

| Username | Password  | admin_channels          |
| :------- | --------- |-------------------------|
| user1    | pass      | ["*"] (All collections) |

### Sample Docs

#### travel.airlines

```JSON
{
  "_id": "airline_1",
  "callsign": "MILE-AIR",
  "collection": "airlines",
  "country": "United States",
  "channels": ["United States"],
  "iata": "Q5",
  "icao": "MLA",
  "name": "40-Mile Air",
  "oid": 10,
  "scope": "travel"
}
```

#### travel.routes

```JSON
{
  "_id": "route_1",
  "airline": "Q5",
  "airlineid": "airline_1",
  "channels": ["United States"],
  "collection": "routes",
  "country": "United States",
  "destinationairport": "HKB",
  "distance": 118.20183585107631,
  "equipment": "CNA",
  "schedule": [
    {
      "day": 0,
      "flight": "Q5188",
      "utc": "12:40:00"
    },
    {
      "day": 0,
      "flight": "Q5630",
      "utc": "21:53:00"
    }
  ],
  "scope": "travel",
  "sourceairport": "FAI",
  "stops": 0
}
```

#### travel.airports

```JSON
{
  "_id": "airport_1",
  "icao": "EGAC",
  "geo": {
    "alt": 15,
    "lon": -5.8725,
    "lat": 54.618056
  },
  "faa": "BHD",
  "type": "airport",
  "scope": "travel",
  "city": "Belfast",
  "tz": "Europe/London",
  "country": "United Kingdom",
  "channels": ["United Kingdom"],
  "collection": "airports",
  "airportname": "Belfast City"
}
```

#### travel.landmarks

``` JSON
{
  "_id": "landmark_1",
  "activity": "see",
  "address": "STF Abisko Mountain Station, Sweden",
  "channels": [
    "United States"
  ],
  "city": "San Francisco",
  "collection": "landmarks",
  "content": "The night visit to the station includes return ticket by chair-lift...",
  "country": "United States",
  "directions": null,
  "email": "lapplandsbokning@stfturist.se",
  "geo": {
    "accuracy": "RANGE_INTERPOLATED",
    "lat": 37.8013,
    "lon": -122.3988
  },
  "hours": "In 2013\\/2014 winter season: Sep 5 - Sep 28 and Nov 1 - Nov 30: Thu-Sat 21:00-1:00;...",
  "name": "Aurora Sky Station",
  "phone": "+46 980 402 00",
  "price": "Sep, Nov 625 SEK, STF member: 525 SEK; Dec-Mar 695 SEK, STF member: 595 SEK",
  "scope": "travel",
  "state": "California",
  "tollfree": null,
  "url": "http:\\/\\/www.auroraskystation.com"
}
```

#### travel.hotels

```JSON
{
  "_id": "hotel_1",
  "address": "1702 18th Street",
  "channels": [
    "United States"
  ],
  "city": "Bakersfield",
  "collection": "hotels",
  "country": "United States",
  "description": "This boutique hotel offers five unique food and beverage venues.",
  "email": null,
  "free_breakfast": true,
  "free_internet": false,
  "free_parking": false,
  "geo": {
    "accuracy": "RANGE_INTERPOLATED",
    "lat": 35.375572,
    "lon": -119.02151
  },
  "image": {
    "@type": "blob",
    "content_type": "image/png",
    "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
    "length": 156627
  },
  "name": "The Padre Hotel",
  "pets_ok": true,
  "phone": null,
  "price": null,
  "public_likes": [
    "John Doe"
  ],
  "reviews": [
    {
      "author": "John Doe",
      "content": "Very nice hotel",
      "date": "2015-07-08 03:14:11 +0300",
      "ratings": {
        "Cleanliness": 5,
        "Location": 3,
        "Overall": 4,
        "Rooms": 5,
        "Service": 5,
        "Sleep Quality": 5,
        "Value": 5
      }
    }
  ],
  "scope": "travel",
  "state": "California",
  "url": "http://www.thepadrehotel.com",
  "vacancy": false
}
```

## 2. names

The 100 name documents in the default collection.

### CBL

| Collections         | #Docs       | Doc ID              |
| :------------------ | ----------- | --------------------|
| _default._default   | 100         | name_1 ... 100      | 

### SG

| Collections         | #Docs       | Doc ID              |
| :------------------ | ----------- | --------------------|
| _default._default   | 100         | name_101 --- 200    |

### SG Config

 | Config      | Value             |
 | ----------- | ------------------|
 | Database    | names             |
 | Port        | 4984 / 4985       |
 | Collections | _default._default |

#### Sync Function

```js
function (doc, oldDoc, meta) {
  if (doc._deleted) {
    channel(oldDoc.channels)
  } else {
    channel(doc.channels)
  }
}
```

#### Users

| Username | Password  | admin_channels |
| :------- | --------- |----------------|
| user1    | pass      | ["*"]          |

### Sample Docs

```JSON
{
  "_id": "name_1",
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
  "likes": [
    "chatting"
  ],
  "memberSince": "2011-05-05",
  "scope": "_default",
  "collection": "_default"
}
```

## 3. posts

### CBL Dataset

| Collections         | #Docs       |
| :------------------ | ----------- |
| _default.posts      | 0           |

### SG Dataset

| Collections         | #Docs       | Doc ID           |
| :------------------ | ----------- | -----------------|
| _default.posts      | 5           | post_1 ... 5     |

**Note:**
* post_1, post_2, and post_3 will have `channels` as ["group1", "group2"].
* post_4, post_5 will have `channels` as ["group2"].

### SG Config

 | Config      | Value             |
 | ----------- | ------------------|
 | Database    | posts             |
 | Port        | 4984 / 4985       |
 | Collections | _default.posts |

#### Sync Function

```js
function (doc, oldDoc, meta) {
  if (doc._deleted) {
    channel(oldDoc.channels)
  } else {
    channel(doc.channels)
  }
}
```

#### Users

| Username | Password  | admin_channels     |
| :------- | --------- |--------------------|
| user1    | pass      | ["group1", "group2"]|

### Sample Docs

```JSON
{
  "_id": "post_1",
  "scope": "_default",
  "collection": "posts",
  "channels": ["group1", "group2"],
  "title": "Post 1",
  "content": "This is content of my post 1",
  "owner": "user1"
}
```
## 4. todo

### CBL Dataset

| Collections         | #Docs       |
| :------------------ | ----------- |
| _default.lists      | 0           |
| _default.tasks      | 0           |
| _default.users      | 0           |

### SG Dataset

| Collections         | #Docs       | Doc ID           |
| :------------------ | ----------- | -----------------|
| _default.lists      | 0           |                  |
| _default.tasks      | 0           |                  |
| _default.users      | 0           |                  |

### SG Config

 | Config      | Value             |
 | ----------- | ------------------|
 | Database    | posts             |
 | Port        | 4984 / 4985       |
 | Collections | _default.lists    |
 | Collections | _default.tasks    |
 | Collections | _default.users    |

#### Sync Function

##### _default.lists

```js
function (doc, oldDoc, meta) {
    var owner = doc._deleted
        ? oldDoc.owner
        : doc.owner;
    requireUser(owner);
    var listChannel = 'lists.' + owner + '.' + doc._id;
    var contributorRole = 'role:' + listChannel + '.contributor';
    role(owner, contributorRole);
    access(contributorRole, listChannel);
    channel(listChannel)
}
```

##### _default.tasks

```js
function (doc, oldDoc, meta) {
    var listId = doc._deleted
        ? oldDoc.taskList.id
        : doc.taskList.id;
    var listOwner = doc._deleted
        ? oldDoc.taskList.owner
        : doc.taskList.owner;
    var listChannel = 'lists.' + listOwner + '.' + listId;
    var contributorRoleName = listChannel + '.contributor';
    var contributorRole = 'role:' + contributorRoleName;
    requireRole(contributorRoleName);
    var tasksChannel = listChannel + '.tasks';
    access(contributorRole, tasksChannel);
    channel(tasksChannel)
}
```

##### _default.users

```js
function (doc, oldDoc, meta) {
    var listId = doc._deleted
        ? oldDoc.taskList.id
        : doc.taskList.id;
    var listOwner = doc._deleted
        ? oldDoc.taskList.owner
        : doc.taskList.owner;
    requireUser(listOwner);
    var listChannel = 'lists.' + listOwner + '.' + listId;
    var contributorRole = 'role:' + listChannel + '.contributor';
    if (!doc._deleted) {
        var username = doc._deleted
            ? oldDoc.username
            : doc.username;
        role(username, contributorRole)
    }
    var usersChannel = listChannel + '.users';
    access(listOwner, usersChannel);
    channel(usersChannel)
}
```

#### Roles

CBG-2490 : SG doesn't support dynamic cross collection access grant via sync function, 
to implement sharing feature with access-grant-user doc, granting the access to a static role that has 
access to the list and its tasks is used as a workaround. 

Before creating a new list in the test, a contributor for the list needs to be created first 
by using SG Admin API as the following cURL command example.

```
curl --location --request POST 'http://<sg-address>:4985/todo/_role/' \
--user "<user>:<password>" \
--header 'Content-Type: application/json' \
--data "{
    \"name\": \"lists.<task-list-owner>.<task-list-doc-id>.contributor\",
    \"collection_access\": {
        \"_default\": {
            \"lists\": {\"admin_channels\": []},
            \"tasks\": {\"admin_channels\": []},
            \"users\": {\"admin_channels\": []}
        }
    }
}"
```

#### Users

| Username | Password  | admin_channels       |
| :------- | --------- |--------------------- |
| user1    | pass      | [] (All collections) |
| user2    | pass      | [] (All collections) |
| user3    | pass      | [] (All collections) |

### Docs

##### _default.lists

| Key      | Type   | Required |Description                       | 
| :------- | ------ | -------- |--------------------------------- |
| _id      | string | Yes      | Document ID in <UUID> format        |
| name     | string | Yes      | List name                         |
| owner    | string | Yes      | User ID of the owner of the list  |

###### Sample

```JSON
{
  "_id": "f2662f3b-828e-4746-bfd1-30ca8506e665",
  "name": "List 1",
  "owner": "user1"
}
```
##### _default.tasks

| Key      | Type   | Required | Description                       | 
| :------- | ------ | -------- | --------------------------------- |
| _id      | string | Yes      | Document ID in <UUID> format      |
| name     | string | Yes      | Task name                         |
| image    | blob   | No       | Optional image                    |
| complete | bool   | Yes      | Complete Status                   |
| list     | dict   | Yes      | Contains two required keys : 'id', doc id of the list and 'owner', owner of the list |

```JSON
{
  "_id": "9077616a-452b-4e7e-a56a-33d1605ff732",
  "name": "Task1",
  "complete": true,
  "image": {
    "@type": "blob",
    "content_type": "image/jpeg",
    "digest": "sha1-7hYMqN2gjvfVtZ6UcYCFZWLWo98=",
    "length": 156627
  },
  "list" : {
    "id": "f2662f3b-828e-4746-bfd1-30ca8506e665",
    "owner" : "user1"  
  }
}
```
##### _default.users

| Key      | Type   | Required | Description                       | 
| :------- | ------ | -------- | --------------------------------- |
| _id      | string | Yes      | Document ID in <list-doc-id>.<username> format. The username is the username to share the list |
| username | string | Yes      | Username to share the list        |
| list     | dict   | Yes      | Contains two required keys : 'id', doc id of the list and 'owner', owner of the list |

```JSON
{
  "_id": "f2662f3b-828e-4746-bfd1-30ca8506e665.user2",
  "username": "user2",
  "list" : {
    "id": "f2662f3b-828e-4746-bfd1-30ca8506e665",
    "owner" : "user1"  
  }
}
```