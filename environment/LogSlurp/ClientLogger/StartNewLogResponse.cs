﻿using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ClientLogger;

internal readonly record struct StartNewLogResponse(string log_id);