//-----------------------------------------------------------------------
// <copyright company="Microsoft Corporation">
//        Copyright (c) Microsoft Corporation.  All rights reserved.
//        Licensed under the MIT license. See LICENSE file in the project root for full license information.
// </copyright>
//-----------------------------------------------------------------------

import { Diagnostics } from './Diagnostics';
import { Simulator } from './components/simulator/Simulator';

// 通常は What-if シミュレータ。接続の切り分けが要るときだけ、#diagnostics で診断画面を開く。
function App() {
  return window.location.hash === '#diagnostics' ? <Diagnostics /> : <Simulator />;
}

export default App;
