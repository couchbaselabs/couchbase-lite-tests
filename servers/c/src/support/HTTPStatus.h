#pragma once

namespace ts::support {
    // The HTTP statuses the server responds with. The values are the status codes themselves, so a
    // status converts to its code with static_cast<int>.
    enum class HTTPStatus : int {
        OK = 200,
        BadRequest = 400,
        NotFound = 404,
        InternalServerError = 500,
    };
}
