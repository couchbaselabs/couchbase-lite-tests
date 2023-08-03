from cbltest import CBLPyTest
from cbltest.api.error import CblTestServerBadResponseError
import pytest

class TestUpdateDatabase:
    @pytest.mark.asyncio
    async def test_update(self, cblpytest: CBLPyTest) -> None:
        bad_attempts = [
            # Empty
            "", 
            
            # Double open bracket
            "test[[", 
            
            # Missing array index
            "test[]", 
            
            # Invalid array index (word instead of number)
            "test[foo]", 
            
            # Array index where property is expected
            "test.[3]", 
            
            # Double closing bracket
            "test[3]]", 
            
            # Invalid array index (negative)
            "contact.email[-1]",

            # name.first is scalar and has no nested properties
            "name.first.secret", 
            
            # name.first is scalar and has no elements
            "name.first[0]", 
            
            # contact.email is an array and has no nested properties
            "contact.email.secret", 
            
            # name is a dictionary and has no elements
            "name[0]"
        ]

        db = (await cblpytest.test_servers[0].create_and_reset_db("names", ["db1"]))[0]

        for attempt in bad_attempts:   
            with pytest.raises(CblTestServerBadResponseError, match="returned 400"):
                async with db.batch_updater() as b:
                    b.upsert_document("_default", "name_1", [{attempt: 5}])

        good_attempts = [
            # Add a brand new root key (with the optional JSON path $ for bonus points)
            "$.test", 

            # Add a new root key, but this time escape the dollar sign
            "\\$.test",
            
            # Add a new root key with a nested key inside
            "test2.nested", 

            # Begin the list of nested keys from the Ministry of Silly Names
            "test2.\\[",
            "test2.\\]",
            "test2.\\.",
            "test2.foo\\[",
            "test2.foo\\]",
            "test2.foo\\."
            "test2.foo\\[bar",
            "test2.foo\\]bar",
            "test2.foo\\.bar"

            
            # Add a new root key that contains an array of size 4
            "test3[3]", 

            # Add a new root key with a silly, but legal, nested key name
            "test4.$",
            
            # Add a key to an existing dictionary
            "name.secret", 
            
            # Add a key with a nested key inside to an existing dictionary
            "name.other_secret.super_secret", 
            
            # Replace dictionary with scalar
            "contact"
            
            # Replace array with scalar
            "likes"]
        
        # Faster to do these as one successful batch updates.  If you want to do 
        # them one at a time edit this loop to match the previous 'bad_attempts' one
        async with db.batch_updater() as b:
            for attempt in good_attempts:  
                b.upsert_document("_default", "name_1", [{attempt: 5}])