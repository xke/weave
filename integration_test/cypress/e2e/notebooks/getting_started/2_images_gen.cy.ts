import {checkWeaveNotebookOutputs} from '../notebooks';

describe('../examples/getting_started/2_images_gen.ipynb notebook test', () => {
    it('passes', () =>
        checkWeaveNotebookOutputs('../examples/getting_started/2_images_gen.ipynb')
    );
});